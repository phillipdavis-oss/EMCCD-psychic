# -*- coding: utf-8 -*-
"""
Created on Mon Feb 02 10:17:34 2015

@author: dvalovcin
"""


from ctypes import *
import os
import time
import numpy as np
import logging
import logging.handlers
log = logging.getLogger("Andor")
log.setLevel(logging.DEBUG)
# Guard against re-import: these are module-level side effects, so without
# this a second import would attach a second copy of every handler and
# double every line in the log.
if not log.handlers:
    handler1 = logging.StreamHandler()
    handler1.setLevel(logging.WARNING)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler1.setFormatter(formatter)
    log.addHandler(handler1)
    # Rotating, not plain FileHandler: this logger runs at DEBUG and
    # fakeAndor logs every single DLL call, so an append-only file grew
    # without bound. Path is anchored to this module because the Andor SDK
    # load below chdir()s.
    handler2 = logging.handlers.RotatingFileHandler(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "TheCameraLog.log"),
        maxBytes=2*1024*1024, backupCount=3)
    handler2.setLevel(logging.DEBUG)
    handler2.setFormatter(formatter)
    log.addHandler(handler2)


class AndorCapabilities(Structure):
    """ Class for retrieving the available parameters of the camera
        http://forge.abcd.harvard.edu/gf/project/storm_control/scmgit/?p=storm_control;a=blob_plain;f=hal4000/andor/andorcontroller.py;hb=ec7d862398760cf292dfc53fc5add8ebc39eeb74

    """
    _fields_ = [("ulSize", c_ulong),
                ("ulAcqModes", c_ulong),
                ("ulReadModes", c_ulong),
                ("ulTriggerModes", c_ulong),
                ("ulCameraType", c_ulong),
                ("ulPixelMode", c_ulong),
                ("ulSetFunctions", c_ulong),
                ("ulGetFunctions", c_ulong),
                ("ulFeatures", c_ulong),
                ("ulPCICard", c_ulong),
                ("ulEMGainCapability", c_ulong),
                ("ulFTReadModes", c_ulong)]

class AndorEMCCD(object):
    
    def __init__(self, wantFake = False):

        self.dll = None
        # Flag to keep track of whether the camera is
        # real or not
        self.amFake = False

        self.cameraSettings = {
            'xPixels': None,
            'yPixels': None,
            'numADChannels': None,
            'curADChannel': None,
            'outputAmp': None,
            'numHSS': None,
            'curHSS': None,
            'HSS': [],
            'numVSS': None,
            'curVSS': None,
            'VSS': [],
            'curAcqMode': None,
            'curReadMode': None,
            'curTrig': None,
            'imageSettings': [],
            'exposureTime': None,
            'gain': None,
            'shutter': None,
            'curShutterInt': None,
            'curShutterEx': None,
        }



        self.registerFunctions(wantFake = wantFake)
        log.debug("About to initialize EMCCD")
        self.dllInitializeRet = None
        ret = self.dllInitialize(b'')
        if ret != 20002:

            log.error("Error initializing camera\n\tCode :{}".format(
                self.parseRetCode(ret)
            ))
            self.dll = None
            self.dllInitializeRet = ret
            self.registerFunctions(wantFake = True)
        self.isCooled = False
        self.temperature = 20 # start off at room temperature
        self.tempRetCode = '' # code to
        # self.cameraSettings = dict() # A dictionary to hold various parameters of the camera

        self.data = None
        self.capabilities = AndorCapabilities(sizeof(c_ulong)*12,0,0,0,0,0,0,0,0,0,0,0)



    def gotoTemperature(self, *args):
        """Sets the specified temperature and goes through a loop to
            wait for it to achieve the desired temperature"""
        temp = args[0][0]
        killFast = args[0][1]
        if not self.isCooled:
            retFlag = self.parseRetCode(self.dllCoolerON())

            if retFlag == 'DRV_NOT_INITIALIZED':
                print('CoolerON: Instrument not initialized')
                return
            elif retFlag == 'DRV_ACQUIRING':
                print('Acquisition running. Cannot turn on cooler')
                return
            elif retFlag == 'DRV_ERROR_ACK':
                print('Cooler card read error')
                return

            self.isCooled = True
        retFlag = self.parseRetCode(self.dllSetTemperature(temp))
        if retFlag == "DRV_SUCCESS":
            log.info("Set temperature to {}C".format(temp))
        else:
            log.warning("Error setting temperature, {}".format(retFlag))

        tempTemp = c_int(0)
        self.tempRetCode = self.parseRetCode(self.dllGetTemperature(tempTemp))
        self.temperature = tempTemp.value
        if not killFast:
            while self.tempRetCode != "DRV_TEMPERATURE_STABILIZED":
                time.sleep(1)
                self.tempRetCode = self.parseRetCode(self.dllGetTemperature(tempTemp))
                self.temperature = tempTemp.value
                log.debug("At new temperature, {}, {}".format(self.temperature, self.tempRetCode))
                # print 'Current temp: {}'.format(self.temperature)
        else:
            while self.tempRetCode != "DRV_TEMPERATURE_STABILIZED" and self.temperature<0:
                time.sleep(1)
                self.tempRetCode = self.parseRetCode(self.dllGetTemperature(tempTemp))
                self.temperature = tempTemp.value

    def getTemperature(self):
        temp = c_int(0)
        self.dllGetTemperature(temp)
        self.temperature = temp.value
        return self.temperature

    def getStatus(self):
        status = c_int(0)
        self.dllGetStatus(status)
        return status.value

    def initialize(self, ad = 0, outputAmp = 0):
        
        # get detector size
        x = c_int(0)
        y = c_int(0)
        self.dllGetDetector(x, y)
        log.info('Detector got. x={}, y={}'.format(x.value, y.value))
        self.cameraSettings['xPixels'] = x.value
        self.cameraSettings['yPixels'] = y.value

        self.setImage([1, 1, 1, x.value, 1, y.value])

        
        # get the number of ad channels
        num = c_int(0)
        self.dllGetNumberADChannels(num)
        self.cameraSettings['numADChannels'] = num.value
        self.setAD(ad)

        # set default output amplifier to EM over convetional.
        self.cameraSettings['outputAmp'] = outputAmp #Prefering EM over conventional gain
        
        # get number of horizontal shift speeds. Then get their values
        self.getHSS()
        
        # ditto for the veritcal ss
        self.getVSS()

        # set the initial HSSp/VSSp to the first one possible
        self.setHSS(0)
        self.setVSS(1)

        # set to the single-scan mode
        self.setAcqMode(1)

        # set to the image acquisition mode
        self.setRead(4)

        # default external triggering
        self.setTrigger(1)

        #default gain/exposure
        self.setExposure(0.5)
        self.setGain(1)

        #SETUP THE SHUTTER
        # assume TTL high, automatic usage, 10ms open/close
        self.setShutterEx(0, 0)

    def setHSS(self, idx):
        log.debug('Setting HSS {}'.format(idx))
        ret = self.dllSetHSSpeed(self.cameraSettings['outputAmp'],
                           idx)
        if ret == 20002:
            self.cameraSettings['curHSS'] = self.cameraSettings['HSS'][idx]
        else:
            log.warning("Setting HSS Failed: {}".format(ret))
        return ret

    def setVSS(self, idx):
        log.debug('Setting VSS {}'.format(idx))
        self.getVSS()
        ret = self.dllSetVSSpeed(idx)
        if ret == 20002:
            self.cameraSettings['curVSS'] = self.cameraSettings['VSS'][idx]
        else:
            log.warning("Setting VSS Failed: {}".format(ret))
        return ret

    def setAD(self, ad=0):
        """Set the current AD channel to the input value"""
        log.debug('Setting AD {}'.format(ad))
        ret =  self.dllSetADChannel(ad)
        if ret == 20002:
            self.cameraSettings['curADChannel'] = ad
        else:
            log.warning("Setting AD Failed: {}".format(ret))
        return ret

    def setAcqMode(self, idx):
        if idx in (0, 6, 7, 8):
            # invalid by the CCD designation
            raise ValueError("Invalid acquisition mode. You shouldn't be here... ({})".format(idx))
        log.debug('Setting acquisition {}'.format(idx))
        # dictionary to retrieve the mode title
        d = {1:'Single Scan', 2:'Accumulate', 3:'Kinetics',
             4:'Fast Kinetics', 5:'Run till abort',
             9:'Time delayed integration'}
        ret = self.dllSetAcquisitionMode(idx)
        if ret == 20002:
            self.cameraSettings['curAcqMode'] = d[idx]
        else:
            log.warning("Setting acquisition Failed: {}".format(ret))
        return ret

    def setRead(self, idx):
        log.debug('Setting Read {}'.format(idx))
        d = {0:"Full Vertical Binning",
             1:"Multi-Track",
             2:"Random-Track",
             3:"Single-Track",
             4:"Image"}
        ret = self.dllSetReadMode(idx)
        if ret == 20002:
            self.cameraSettings['curReadMode'] = d[idx]
        else:
            log.warning("Setting Read Failed: {}".format(ret))
        return ret

    def setTrigger(self, idx):
        log.debug('Setting Trigger {}'.format(idx))
        d = {0:"Internal",
             1:"External"}
        ret = self.dllSetTriggerMode(idx)
        if ret == 20002:
            self.cameraSettings['curTrig'] = d[idx]
        else:
            log.warning("Setting Trigger Failed: {}".format(ret))
        return ret

    def setImage(self, vals):
        log.debug('Setting image {}'.format(vals))
        ret = self.dllSetImage(vals[0], vals[1],
                                vals[2], vals[3],
                                vals[4], vals[5])
        if ret == 20002:
            self.cameraSettings['imageSettings'] = vals  #Set the default size for the image to be collected
        else:
            log.warning("setimage: {}".format(ret))
        return ret

    def getHSS(self):
        num = c_int(0)
        self.dllGetNumberHSSpeeds(self.cameraSettings['curADChannel'], self.cameraSettings['outputAmp'],
                                  num)
        self.cameraSettings['numHSS'] = num.value
        self.cameraSettings['HSS'] = [] #list of available speeds
        speed = c_float(0)
        for idx in range(self.cameraSettings['numHSS']):
            self.dllGetHSSpeed(self.cameraSettings['curADChannel'],
                               self.cameraSettings['outputAmp'],
                               idx, speed)
            self.cameraSettings['HSS'].append(speed.value)

    def getVSS(self):
        """Request the number of vertical shift speeds the camera has. Then iterate
         over the possible choices and find their corresponding speed """

        num = c_int(0)
        speed = c_float(0)
        self.dllGetNumberVSSpeeds(num)
        self.cameraSettings['numVSS'] = num.value
        self.cameraSettings['VSS'] = [] #list of available speeds
        for idx in range(self.cameraSettings['numVSS']):
            self.dllGetVSSpeed(idx, speed)
            self.cameraSettings['VSS'].append(speed.value)

    def setExposure(self, exp):
        ret = self.dllSetExposureTime(exp)
        if ret == 20002:
            self.cameraSettings['exposureTime'] = exp
        return ret

    def setGain(self, val):
        ret = self.dllSetEMCCDGain(val)
        if ret == 20002:
            self.cameraSettings['gain'] = val
        return ret

    def _getImageDims(self):
        """
        :return: (x, y) pixel dimensions of the image for the current
        imageSettings/read mode.
        """
        # the image settings, for readability
        image = self.cameraSettings["imageSettings"]

        # figure out the dimensions of the image based on the specified settings
        # think I need a +1 since each end is inclusive
        x = int(round(
            (image[3]-image[2])/image[0]
        )) + 1


        # I don't fully understand why the "int(image[1]==1)" is here.
        # It came about from testing, and it needed it. I don't know
        y = int(round(
            (image[5]-image[4])/image[1]
        )) + int(image[1]==1)
        if 'Binning' in self.cameraSettings['curReadMode']:
            y = 1
        # if image[0] != 1 or image[1] != 1:
        #     print "Debugging: Non-standard binning"
        #     print image
        #     print x,y
        return x, y

    def getAcquisitionTimings(self):
        """
        :return: (exposure, accumulate, kinetic) in seconds, as the camera
        actually quantized them, or None if the call isn't available or fails.

        Worth logging before every acquisition: cameraSettings['exposureTime']
        is only what we *asked* for. If the kinetic time comes back at 15s for
        a 0.5s exposure, the camera is spending that time reading out (or
        accumulating) and nothing outside this program can fix it. If it comes
        back at ~0.5s and the acquisition still takes 15s, the camera is
        sitting on the external trigger instead.
        """
        if self.dllGetAcquisitionTimings is None:
            return None
        exposure, accumulate, kinetic = c_float(0), c_float(0), c_float(0)
        ret = self.dllGetAcquisitionTimings(exposure, accumulate, kinetic)
        if ret != 20002:
            log.debug("GetAcquisitionTimings failed: {}".format(
                self.parseRetCode(ret)))
            return None
        return exposure.value, accumulate.value, kinetic.value

    def getReadoutTime(self):
        """
        :return: the camera's own readout time in seconds, or None on a
        pre-2.9 SDK (or if the call fails).
        """
        return self._getSingleTiming(self.dllGetReadOutTime, "GetReadOutTime")

    def getKeepCleanTime(self):
        """
        :return: the camera's keep-clean time in seconds, or None on a
        pre-2.9 SDK (or if the call fails).
        """
        return self._getSingleTiming(self.dllGetKeepCleanTime,
                                     "GetKeepCleanTime")

    def _getSingleTiming(self, func, name):
        if func is None:
            return None
        val = c_float(0)
        ret = func(val)
        if ret != 20002:
            log.debug("{} failed: {}".format(name, self.parseRetCode(ret)))
            return None
        return val.value

    def describeSettings(self):
        """
        :return: one line naming everything that governs how long an
        acquisition takes. Logged at the start of an exposure so the log
        alone is enough to tell a slow readout from a slow trigger.
        """
        return ("read={curReadMode} trig={curTrig} acq={curAcqMode} "
                "AD={curADChannel} amp={outputAmp} HSS={curHSS} VSS={curVSS} "
                "image={imageSettings} exp={exposureTime} gain={gain}".format(
                    **self.cameraSettings))

    def estimateReadoutTime(self):
        """
        :return: how long, in seconds, the camera will spend reading out a
        frame with the current settings, or None if it can't be determined.

        Prefers the camera's own answer (GetReadOutTime, else the kinetic
        cycle time from GetAcquisitionTimings minus the exposure), falling
        back to arithmetic only when neither call exists.

        That fallback is deliberately asymmetric. GetVSSpeed reports
        microseconds per row shift, but GetHSSpeed reports MHz on the
        iXon/Newton (see the docstring on its binding), so the horizontal
        term is pixels/rate, not pixels*rate. Having those units the same
        way round is what made this function claim 0.03s for a full-frame
        readout that really takes ~13s at the 0.05MHz conventional speed.
        """
        readout = self.getReadoutTime()
        if readout is not None:
            return readout

        timings = self.getAcquisitionTimings()
        if timings is not None:
            exposure, _, kinetic = timings
            if kinetic > exposure:
                return kinetic - exposure

        hss = self.cameraSettings['curHSS']
        vss = self.cameraSettings['curVSS']
        if not hss or vss is None:
            return None
        x, y = self._getImageDims()
        return y * vss / 1e6 + x * y / (hss * 1e6)

    def getImage(self):
        """
        :return: array of image value

        This function will automatically read the image from the CCD and
        then return a numpy array of the correct shape
        """

        x, y = self._getImageDims()

        retdata = (c_int * (x * y))(-1)

        retval = self.dllGetAcquiredData(retdata, x * y )
        if retval != 20002:
            return retval



        # Pull the ctypes buffer straight into numpy instead of appending
        # x*y (640,000 for a full frame) elements one at a time in Python.
        # as_array() is a zero-copy view onto retdata; .astype(int) makes an
        # owned int64 copy, matching what the old list-based path produced and
        # decoupling the result from the lifetime of the ctypes buffer.
        retnums = np.ctypeslib.as_array(retdata).reshape(y, x).astype(int)

        # There's also some concern of how exactly the array is returned in
        # relation to a full image.
        retnums = np.fliplr(retnums)


        return retnums

    def setShutterEx(self, intMode, exMode):
        """
        :param intMode: internal mode
        :param exMode: external mode
        0=auto, 1=open, 2=close
        :return:
        """

        # screw you, you only get TTL high and 10ms open/closing times for now
        ret = self.dllSetShutterEx(1, intMode, 10, 10, exMode)

        # I'm too tired to justify this
        d = {0: "Fully Auto",
             1: "Permanently Open",
             2: "Permanently Closed"}
        if ret == 20002:
            self.cameraSettings["shutter"] = [intMode, exMode]
            self.cameraSettings["curShutterInt"] = d[intMode]
            self.cameraSettings["curShutterEx"] = d[exMode]
        return ret

    def getCapabilities(self):
        ret = self.dllGetCapabilities(self.capabilities)
        print("GetCapabilities: {}".format(self.parseRetCode(ret)))

    def registerFunctions(self, wantFake = False):
        """ This function serves to import all of the functions
        from the DLL, define them as the class's own for neatness, and
        set up prototypes.
        
        All functions follow the convention self.dllFunctionName so that it
        is easier to see which are coming directly from the dll."""
        name = "atmcd64d"
        if wantFake:
            from fakeAndor import fAndorEMCCD
            dll = fAndorEMCCD()
            self.amFake = True
        else:
            try:
                dll = CDLL(name) #Change this to the appropriate name
            except:
                curdir = os.getcwd()
                try:
                    # The SDK dir has to be the cwd for the DLL's own
                    # dependencies to resolve. Restore the cwd in a finally,
                    # not on each branch -- anything writing a relative path
                    # (e.g. Settings.txt) while we're chdir'd would otherwise
                    # land in the SDK directory.
                    os.chdir(r'C:\Program Files\Andor SDK')
                    dll = CDLL(name)
                except:
                    log.error('Error loading the DLL. Using fake')
                    # from fakeAndor import fAndorEMCCD
                    import fakeAndor as FA
                    dll = FA.fAndorEMCCD()
                    self.amFake = True
                    dll.Initialize.retWeights = ((1,), -2)
                    dll.Initialize = FA.myCallable(lambda x: None, 'InitializeMissingDLL')
                finally:
                    os.chdir(curdir)
        
        self.dll = dll # For if it's ever needed to call things directly
        """
        AbortAcquisition: This function aborts the current
        acquisition if one is active.

        Parameters
        ----------
        None

        Return
        ------
        unsigned int
            DRV_SUCCESS             Acquisition aborted.
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_IDLE                The system is not currently acquiring.
            DRV_VXDNOTINSTALLED     VxD not loaded.
            DRV_ERROR_ACK           Unable to communicate with card.

        """
        self.dllAbortAcquisition = dll.AbortAcquisition
        self.dllAbortAcquisition.restype = c_uint
        self.dllAbortAcquisition.argtypes = []
        
        
        """
        CancelWait: This function restarts a thread which is sleeping within
        the WaitForAcquisition function. The sleeping thread will return from
        WaitForAcquisition with a value not equal to DRV_SUCCESS.
        
        Parameters
        ----------
        None
        
        Return
        ------
        unsigned int
            DRV_SUCCESS         Thread restarted successfully
        """
        self.dllCancelWait = dll.CancelWait
        self.dllCancelWait.restype = c_uint
        self.dllCancelWait.argtypes = []
        
        """
        CoolerON: Switches ON the cooling. The rate of temperature change is 
        controlled until the temperature is within 3deg of the set value. 
        Control is returned immediately to the calling application.
        
        Parameters
        ----------
        None
        
        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
            DRV_ACQUIRING       Acquisition in progress.
            DRV_ERROR_ACK       Unable to communicate with card.
        """
        self.dllCoolerON = dll.CoolerON
        self.dllCoolerON.restype = c_uint
        self.dllCoolerON.argtypes = []
        
        """
        CoolerOFF: Switches OFF the cooling. The rate of temperature change is 
        controlled until the temperature reaches 0º. Control is returned 
        immediately to the calling application.
        
        Parameters
        ----------
        None
        
        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
            DRV_ACQUIRING       Acquisition in progress.
            DRV_ERROR_ACK       Unable to communicate with card.
        """
        self.dllCoolerOFF = dll.CoolerOFF
        self.dllCoolerOFF.restype = c_uint
        self.dllCoolerOFF.argtypes = []

        """
        GetAcquiredData: This function will return the data from the last
        acquisition. The data are returned as long integers (32-bit signed
        integers). The “array” must be large enough to hold the complete data set.

        Parameters
        ----------
        long* array: pointer to data storage allocated by the user.
        long size: total number of pixels.

        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
            DRV_ACQUIRING       Acquisition in progress.
            DRV_ERROR_ACK       Unable to communicate with card.
            DRV_P1INVALID       Invalid pointer (i.e. NULL).
            DRV_P2INVALID       Array size is too small.
        """
        self.dllGetAcquiredData = dll.GetAcquiredData
        self.dllGetAcquiredData.resType = c_uint
        self.dllGetAcquiredData.argtypes = [POINTER(c_long), c_long]

        """
        GetCapabilities: This function will fill in an AndorCapabilities
        structure with the capabilities associated with the connected camera.
        Before passing the address of an AndorCapabilites structure to the
        function the ulSize member of the structure should be set to the size
        of the structure. In C++ this can be done with the line:
            caps->ulSize = sizeof(AndorCapabilities);
        Individual capabilities are determined by examining certain bits and
        combinations of bits in the member variables of the AndorCapabilites
        structure. The next few pages contain a summary of the capabilities
        currently returned.

        Parameters
        ----------
        Andor capabilities* caps: the capabilities structure to be filled in.

        Return
        ------
        unsigned int
            DRV_SUCCESS         Capabilities returned
            DRV_NOT_INITIALIZED System not initialized.
            DRV_P1INVALID       Invalid caps parameter (i.e. NULL).
        """
        self.dllGetCapabilities = dll.GetCapabilities
        self.dllGetCapabilities.resType = c_uint
        self.dllGetCapabilities.argtypes = [POINTER(AndorCapabilities)]




        """
        GetDetector: This function returns the size of the detector in 
        pixels. The horizontal axis is taken to be the axis parallel to the
        readout register.
        
        Parameters
        ----------
        int* xpixels: number of horizontal pixels.
        int* ypixels: number of vertical pixels.
        
        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
            DRV_ACQUIRING       Acquisition in progress.
        """
        self.dllGetDetector = dll.GetDetector
        self.dllGetDetector.resType = c_uint
        self.dllGetDetector.argtypes = [POINTER(c_int), POINTER(c_int)]
        
        """
        GetHSSpeed: As your Andor Solis system is capable of operating at more 
        than one horizontal shift speed this function will return the actual 
        speeds available. The value returned is in microseconds per pixel shift 
        (in MHz on idus, iXon & Newton).
        
        Parameters
        ----------
        int channel: the AD channel.
        int type: output amplification.
            Valid values: 
                0 electron multiplication.
                1 conventional.
        int index: speed required
            Valid values 0 to NumberSpeeds-1 where NumberSpeeds is value 
                returned in first parameter after a call to GetNumberHSSpeeds().
        float* speed: speed in microseconds per pixel shift (in MHz on iXon).
        
        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
            DRV_ACQUIRING       Acquisition in progress.
        """
        self.dllGetHSSpeed = dll.GetHSSpeed
        self.dllGetHSSpeed.resType = c_uint
        self.dllGetHSSpeed.argtypes = [c_int, c_int, c_int, POINTER(c_float)]
        
        """
        GetMostRecentImage: This function will update the data array with the 
        most recently acquired image in any acquisition mode. The data are
        returned as long integers (32-bit signed integers). The "array" must 
        be exactly the same size as the complete image.
        
        Parameters
        ----------
        long* array: pointer to data storage allocated by the user.
        unsigned long size: total number of pixels.
        
        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
            DRV_ERROR_ACK       Unable to communicate with card.
            DRV_P1INVALID       Invalid pointer (i.e. NULL).
            DRV_P2INVALID       Array size is too small.
            DRV_NO_NEW_DATA     There is no new data yet.
        """
        self.dllGetMostRecentImage = dll.GetMostRecentImage
        self.dllGetMostRecentImage.restype = c_uint
        self.dllGetMostRecentImage.argtypes = [POINTER(c_long), c_ulong]
            
        """
        GetNumberADChannels: As your Andor Solis system may be capable of 
        operating with more than one A-D converter, this function will tell 
        you the number available.
        
        Parameters
        ----------
            int* number: number of allowed channels
            
        Return
        ------
        unsigned int
            DRV_SUCCESS         Number of channels returned.
        """
        self.dllGetNumberADChannels = dll.GetNumberADChannels
        self.dllGetNumberADChannels.restype = c_uint
        self.dllGetNumberADChannels.argtypes = [POINTER(c_int)]
            
        """
        GetNumberHSSpeeds: As your Andor Solis system may be capable of operating
        at more than one horizontal shift speed this function will return the actual
        number of speeds available.
        
        Parameters
        ----------
        int channel: the AD channel.
        int type: output amplification.
            Valid values: 
                0 electron multiplication.
                1 conventional.
        int* number: number of allowed horizontal speeds

        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
            DRV_ACQUIRING       Acquisition in progress.
            DRV_P1INVALID       Acquisition channel
            DRV_P2INVALID       Acquisition horizontal read mode
        """
        self.dllGetNumberHSSpeeds = dll.GetNumberHSSpeeds
        self.dllGetNumberHSSpeeds.restype = c_uint
        self.dllGetNumberHSSpeeds.argtypes = [c_int, c_int, POINTER(c_int)]
            
        """
        GetNumberVSSpeeds: As your Andor Solis system may be capable of operating
        at more than one vertical shift speed this function will return the actual
        number of speeds available.
        
        Parameters
        ----------
        int* number: number of allowed vertical speeds

        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
            DRV_ACQUIRING       Acquisition in progress.
            DRV_P1INVALID       Acquisition channel
            DRV_P2INVALID       Acquisition horizontal read mode
        """
        self.dllGetNumberVSSpeeds = dll.GetNumberVSSpeeds
        self.dllGetNumberVSSpeeds.restype = c_uint
        self.dllGetNumberVSSpeeds.argtypes = [POINTER(c_int)]
            
        """
        GetStatus: This function will update the data array with the 
        most recently acquired image in any acquisition mode. The data are
        returned as long integers (32-bit signed integers). The "array" must 
        be exactly the same size as the complete image.
        
        Parameters
        ----------
        int* status: current status
            DRV_IDLE                    IDLE waiting on instructions.
            DRV_TEMPCYCLE               Executing temperature cycle.
            DRV_ACQUIRING               Acquisition in progress.
            DRV_ACCUM_TIME_NOT_MET      Unable to meet Accumulate cycle time.
            DRV_KINETIC_TIME_NOT_MET    Unable to meet Kinetic cycle time.
            DRV_ERROR_ACK               Unable to communicate with card.
            DRV_ACQ_BUFFER              Computer unable to read the data via the
                                            ISA slotat the required rate.
            DRV_SPOOLERROR              Overflow of the spool buffer.

        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
        """
        self.dllGetStatus = dll.GetStatus
        self.dllGetStatus.restype = c_uint
        self.dllGetStatus.argtypes = [POINTER(c_int)]
        
        """
        GetTemperature: This function returns the temperature of the detector to 
        the nearest degree. It also gives the status of cooling process.
        
        Parameters
        ----------
        int* temperature: temperature of the detector
        
        Return
        ------
        unsigned int
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_ERROR_ACK           Unable to communicate with card.
            DRV_TEMP_OFF            Temperature is OFF.
            DRV_TEMP_STABILIZED     Temperature has stabilized at set point.
            DRV_TEMP_NOT_REACHED    Temperature has not reached set point.
        """
        self.dllGetTemperature = dll.GetTemperature
        self.dllGetTemperature.restype = c_uint
        self.dllGetTemperature.argtypes = [POINTER(c_int)]
        
        """
        GetVSSpeed: As your Andor Solis system maybe capable of operating at 
        more than one vertical shift speed this function will return the actual 
        speeds available. The value returned is in microseconds per pixel shift.
        
        Parameters
        ----------
        int channel: the AD channel.
        int type: output amplification.
            Valid values: 
                0 electron multiplication.
                1 conventional.
        int index: speed required
            Valid values 0 to NumberSpeeds-1 where NumberSpeeds is value 
                returned in first parameter after a call to GetNumberHSSpeeds().
        float* speed: speed in microseconds per pixel shift (in MHz on iXon).
        
        Return
        ------
        unsigned int
            DRV_SUCCESS         Temperature controller switched ON.
            DRV_NOT_INITIALIZED System not initialized.
            DRV_ACQUIRING       Acquisition in progress.
        """
        self.dllGetVSSpeed = dll.GetVSSpeed
        self.dllGetVSSpeed.resType = c_uint
        self.dllGetVSSpeed.argtypes = [c_int, POINTER(c_float)]
        
        """
        Initialize: This function will initialize the Andor Solis System. As 
        part of the initialization procedure on some cameras (i.e. Classic, 
        Istar and earlier iXion) the DLL will need access the following file:
            DETECTOR.INI which contains information relating to the detector
            head, number pixels, readout speeds etc.
        
        Parameters
        ----------
        char* directory: Path to the directory containing the files
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             System fully initialized.
            DRV_VXDNOTINSTALLED     VxD not loaded
            DRV_INIERROR            Unable to load “DETECTOR.INI”.
            DRV_COFERROR            Unable to load “*.COF”.
            DRV_FLEXERROR           Unable to load “*.RBF”.
            DRV_ERROR_ACK           Unable to communicate with card.
            DRV_ERROR_FILELOAD      Unable to load “*.COF” or “*.RBF” files.
            DRV_ERROR_PAGELOCK      Unable to acquire lock on requested memory.
            DRV_USBERROR            Unable to detect USB device or not USB2.0.
        """
        self.dllInitialize = dll.Initialize
        self.dllInitialize.restype = c_uint
        self.dllInitialize.argtypes = [c_char_p]
        
        """
        PrepareAcquisition: This function reads the current acquisition setup 
        and allocates and clears any memory that will be used during the
        acquisition. The function call is not required as it will be called
        automatically by the StartAcquisition function if it has not already
        been called externally. However for long kinetic series acquisitions 
        the time to allocate and clear any memory can be quite long which can
        result in a long delay between calling StartAcquisition and the acquisition
        actually commencing. For iDus, there is an additional delay caused by the
        camera being set-up with any new acquisition parameters. Calling 
        PrepareAcquisition first will reduce this delay in the StartAcquisition call.
        
        Parameters
        ----------
        NONE
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Acquisition prepared.
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_VXDNOTINSTALLED     VxD not loaded
            DRV_ERROR_ACK           Unable to communicate with card.
            DRV_INIERROR            Unable to load “DETECTOR.INI”.
            DRV_ACQERROR            Acquisition Setting Invalid 
            DRV_ERROR_PAGELOCK      Unable to acquire lock on requested memory.
            DRV_INVALID_FILTER      Filter not available for current acquisition
            DRV_IOCERROR            Integrate On Chip setup error
        """
        self.dllPrepareAcquisition = dll.PrepareAcquisition
        self.dllPrepareAcquisition.restype = c_uint
        self.dllPrepareAcquisition.argtypes = []
        
        """
        SetAcquisitionMode: This function will set the acquisition mode to be 
        used on the next StartAcquisition.
        
        Parameters
        ----------
        int mode: the acquisition mode.
            Valid values: 0,6,7,8 Reserved DO NOT USE
                1 Single Scan
                2 Accumulate
                3 Kinetics
                4 Fast Kinetics
                5 Run till abort
                9 Time Delayed Integration (requires special files)
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Acquisition mode set.
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_P1INVALID           Acquisition mode invalid
        """
        self.dllSetAcquisitionMode = dll.SetAcquisitionMode
        self.dllSetAcquisitionMode.restype = c_uint
        self.dllSetAcquisitionMode.argtypes = [c_uint]
        
        """
        SetADChannel: This function will set the AD channel to one of the possible
        A-Ds of the system. It will be used for subsequent acquisitions.
        
        Parameters
        ----------
        int index: the channel to be used
            Valid values: 0 to GetNumberADChannels-1
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Value for gain accepted.
            DRV_P1INVALID           Index out or range
        """
        self.dllSetADChannel = dll.SetADChannel
        self.dllSetADChannel.restype = c_uint
        self.dllSetADChannel.argtypes = [c_uint]



        """
        SetCoolerMode: This function determines whether the fan is switched
        off when an application ends.

        Parameters
        ----------
        int mode:
            1 – Temperature is maintained on ShutDown
            0 – Returns to ambient temperature on ShutDown

        Return
        ------
        unsigned int
            DRV_SUCCESS             Parameters set.
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_P1INVALID           State parameter was not zero or one.
        """
        self.dllSetCoolerMode = dll.SetCoolerMode
        self.dllSetCoolerMode.restype = c_uint
        self.dllSetCoolerMode.argtypes = [c_uint]


        """
        SetEMCCDGain: Allows the user to change the amplitude of clock voltages 
        thereby amplifying the signal. Gain values between 0 and 255 are permitted.
        
        Parameters
        ----------
        int gain: amount of gain applied.
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Value for gain accepted.
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_I2CTIMEOUT          I2C command timed out.
            DRV_I2CDEVNOTFOUND      I2C device not present.
            DRV_ERROR_ACK           Unable to communicate with card.
            DRV_P1INVALID           Gain value invalid
        """
        self.dllSetEMCCDGain = dll.SetEMCCDGain
        self.dllSetEMCCDGain.restype = c_uint
        self.dllSetEMCCDGain.argtypes = [c_uint]
        
        """
        SetExposureTime: This function will set the exposure time to the nearest 
        valid value not less than the given value. The actual exposure time used 
        is obtained by GetAcquisitionTimings. See section on Acquisition Modes 
        for further details.

        Parameters
        ----------
        float time: the exposure time in seconds.
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Exposure time accepted.
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_P1INVALID           Exposure time invalid
        """
        self.dllSetExposureTime = dll.SetExposureTime
        self.dllSetExposureTime.restype = c_uint
        self.dllSetExposureTime.argtypes = [c_float]

        """
        GetAcquisitionTimings: This function will return the current "valid"
        acquisition timing information, i.e. what the camera actually
        quantized the requested settings to. For a Single Scan the kinetic
        time is the whole frame time -- exposure plus readout plus keep
        clean -- which is what WaitForAcquisition really blocks for.

        GetReadOutTime / GetKeepCleanTime break that number down further.
        They only exist in SDK 2.9 and later, so all three are bound
        defensively below; a missing one leaves its dll* attribute as None
        rather than failing to load the camera.

        Parameters
        ----------
        float* exposure:   valid exposure time in seconds
        float* accumulate: valid accumulate cycle time in seconds
        float* kinetic:    valid kinetic cycle time in seconds
        (GetReadOutTime and GetKeepCleanTime each take a single float*.)

        Return
        ------
        unsigned int
            DRV_SUCCESS             Timing information returned.
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_INVALID_MODE        Acquisition or readout mode not available.
        """
        for timingName, numArgs in (("GetAcquisitionTimings", 3),
                                    ("GetReadOutTime", 1),
                                    ("GetKeepCleanTime", 1)):
            try:
                timingFunc = getattr(dll, timingName)
            except AttributeError:
                # Purely diagnostic calls, so an old DLL that lacks them
                # should degrade, not refuse to run the camera.
                log.debug("DLL has no {}; timing diagnostics reduced".format(
                    timingName))
                setattr(self, "dll" + timingName, None)
                continue
            timingFunc.restype = c_uint
            timingFunc.argtypes = [POINTER(c_float)] * numArgs
            setattr(self, "dll" + timingName, timingFunc)
        
        """
        SetGain: I believe set EMCCDGain is prefered 
        """
        self.dllSetGain = dll.SetGain
        self.dllSetGain.restype = c_uint
        self.dllSetGain.argtypes = [c_float]
        
        """
        SetHSSpeed: This function will set the horizontal speed to one of the
        possible speeds of the system. It will be used for subsequent acquisitions.
        
        Parameters
        ----------
        int type: output amplification.
        Valid values: 
            0 electron multiplication.
            1 conventional.
        int index: the horizontal speed to be used
            Valid values 0 to GetNumberHSSpeeds-1
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Shutter set
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_P1INVALID           Invalid Mode
            DRV_P2INVALID           Index out of range
        """
        
        self.dllSetHSSpeed = dll.SetHSSpeed
        self.dllSetHSSpeed.restype = c_uint
        self.dllSetHSSpeed.argtypes = [c_uint, c_uint]
        
        
        """
        SetImage: This function will set the horizontal and vertical binning to
        be used when taking a full resolution image.
        
        Parameters
        ----------
        int hbin: number of pixels to bin horizontally.
        int vbin: number of pixels to bin vertically.
        int hstart: Start column (inclusive).
        int hend: End column (inclusive).
        int vstart: Start row (inclusive).
        int vend: End row (inclusive).
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Shutter set
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_P1INVALID           Binning parameter invalid
            DRV_P2INVALID           Binning parameter invalid
            DRV_P3INVALID           Sub-area coordinate is invalid
            DRV_P4INVALID           Sub-area coordinate is invalid
            DRV_P5INVALID           Sub-area coordinate is invalid
            DRV_P6INVALID           Sub-area coordinate is invalid
        """
        
        self.dllSetImage = dll.SetImage
        self.dllSetImage.restype = c_uint
        self.dllSetImage.argtypes = [c_uint, c_uint, c_uint, c_uint, c_uint, c_uint]
        
        """
        SetReadMode: This function will set the readout mode to be used on the 
        subsequent acquisitions.
        
        Parameters
        ----------
        int mode: readout mode
            Valid values: 
                0 Full Vertical Binning
                1 Multi-Track
                2 Random-Track
                3 Single-Track
                4 Image
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Readout mode set.
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_P1INVALID           Invalid readoutmode passed
        """
        
        self.dllSetReadMode = dll.SetReadMode
        self.dllSetReadMode.restype = c_uint
        self.dllSetReadMode.argtypes = [c_uint]
        
        """
        SetShutter: This function sets the shutter parameters.
        
        Parameters
        ----------
        int type:
            0 Output TTL low signal to open shutter
            1 Output TTL high signal to open shutter
        int mode:
            0 Auto
            1 Open
            2 Close
        int closingtime: Time shutter takes to close (milliseconds)
        int openingtime: Time shutter takes to open (milliseconds)
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Shutter set
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_ERROR_ACK           Unable to communicate with card.
            DRV_P1INVALID           Invalid type
            DRV_P2INVALID           Invalid mode
            DRV_P3INVALID           Invalid time to open
            DRV_P4INVALID           Invalid time to close
        """
        self.dllSetShutter = dll.SetShutter
        self.dllSetShutter.restype = c_uint
        self.dllSetShutter.argtypes = [c_int, c_int, c_int, c_int]
        
        """
        SetShutterEx: This function sets the shutter parameters.
        ****NOTE: No documentation is provided on the difference between
        SetShutter and SetShutterEx, aside from the presence of the fifth 
        input arg.
        
        Parameters
        ----------
        int type:
            0 Output TTL low signal to open shutter
            1 Output TTL high signal to open shutter
        int mode:
            0 Auto
            1 Open
            2 Close
        int closingtime: Time shutter takes to close (milliseconds)
        int openingtime: Time shutter takes to open (milliseconds)
        int external_mode:
            0 Auto
            1 Open
            2 Close
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Shutter set
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_ERROR_ACK           Unable to communicate with card.
            DRV_P1INVALID           Invalid type
            DRV_P2INVALID           Invalid mode
            DRV_P3INVALID           Invalid time to open
            DRV_P4INVALID           Invalid time to close
        """
        self.dllSetShutterEx = dll.SetShutterEx
        self.dllSetShutterEx.restype = c_uint
        self.dllSetShutterEx.argtypes = [c_int, c_int, c_int, c_int]
        
        """
        SetTemperature: This function will set the exposure time to the nearest 
        valid value not less than the given value. The actual exposure time used 
        is obtained by GetAcquisitionTimings. See section on Acquisition Modes 
        for further details.

        Parameters
        ----------
        float time: the exposure time in seconds.
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Exposure time accepted.
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_P1INVALID           Exposure time invalid
        """
        self.dllSetTemperature = dll.SetTemperature
        self.dllSetTemperature.restype = c_uint
        self.dllSetTemperature.argtypes = [c_int]
        
        """
        SetTriggerMode: This function will set the trigger mode to either 
        Internal, External or External Start
        
        Parameters
        ----------
        int mode: trigger mode
            Valid values:
                0 Internal
                1 External
                6 External Start (only valid in Fast Kinetics mode)
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Trigger mode set
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_P1INVALID           Trigger mode invalid
        """
        
        self.dllSetTriggerMode = dll.SetTriggerMode
        self.dllSetTriggerMode.restype = c_uint
        self.dllSetTriggerMode.argtypes = [c_int]
        
        """
        SetVSSpeed: This function will set the vertical speed to one of the
        possible speeds of the system. It will be used for subsequent acquisitions.
        
        Parameters
        ----------
        int index: the horizontal speed to be used
            Valid values 0 to GetNumberHSSpeeds-1
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Shutter set
            DRV_NOT_INITIALIZED     System not initialized.
            DRV_ACQUIRING           Acquisition in progress.
            DRV_P1INVALID           Index out of range
        """
        self.dllSetVSSpeed = dll.SetVSSpeed
        self.dllSetVSSpeed.restype = c_uint
        self.dllSetVSSpeed.argtypes = [c_uint]
        
        """
        ShutDown: This function will close the AndorMCd system down.
        
        Parameters
        ----------
        NONE
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             System shut down.
        """
        self.dllShutDown = dll.ShutDown
        self.dllShutDown.restype = c_uint
        self.dllShutDown.argtypes = []
        
        """
        StartAcquisition: This function starts an acquisition. The status of 
        the acquisition can be monitored via GetStatus().
        
        Parameters
        ----------
        NONE
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Acquisition started
            DRV_NOT_INITIALIZED     System not initialized
            DRV_ACQUIRING           Acquisition in progress
            DRV_VXDNOTINSTALLED     VxD not loaded
            DRV_ERROR_ACK           Unable to communicate with card.
            DRV_INIERROR            Unable to load “DETECTOR.INI”.
            DRV_ERROR_PAGELOCK      Unable to acquire lock on requested memory.
            DRV_INVALID_FILTER      Filter not available for current position
        """
        self.dllStartAcquisition = dll.StartAcquisition
        self.dllStartAcquisition.restype = c_uint
        self.dllStartAcquisition.argtypes = []
        
        """
        WaitForAcquisition: WaitForAcquisition can be called after an acquisition
        is started using StartAcquisition to put the calling thread to sleep until
        an Acquisition Event occurs. This can be used as a simple alternative to 
        the functionality provided by the SetDriverEvent function, as all Event 
        creation and handling is performed internally by the SDK library.
        
        Like the SetDriverEvent functionality it will use less processor resources
        than continuously polling with the GetStatus function. If you wish to 
        restart the calling thread without waiting for an Acquisition event,
        call the function CancelWait.
        
        An Acquisition Event occurs each time a new image is acquired during an
        Accumulation, Kinetic Series or Run-Till-Abort acquisition or at the 
        end of a Single Scan Acquisition
        
        Parameters
        ----------
        NONE
        
        Return
        ------
        unsigned int
            DRV_SUCCESS             Acquisition event occurred
            DRV_NO_NEW_DATA         Non-Acquisition Event occurred.(e.g. CancelWait() called)
        """
        self.dllWaitForAcquisition = dll.WaitForAcquisition
        self.dllWaitForAcquisition.restype = c_uint
        self.dllWaitForAcquisition.argtypes = []

    @staticmethod
    def parseRetCode(value):
        """Pass in the return value of a function and this will return
         values <0 correspond to personal error codes
        :rtype : String of the corresponding error message
        the string which it represents"""
        values = {
            -1   : 'FakeAndor',
            -2   : 'MissingDLL',
            20001: 'DRV_ERROR_CODES',
            20002: 'DRV_SUCCESS',
            20003: 'DRV_VXDNOTINSTALLED',
            20004: 'DRV_ERROR_SCAN',
            20005: 'DRV_ERROR_CHECK_SUM',
            20006: 'DRV_ERROR_FILELOAD',
            20007: 'DRV_UNKNOWN_FUNCTION',
            20008: 'DRV_ERROR_VXD_INIT',
            20009: 'DRV_ERROR_ADDRESS',
            20010: 'DRV_ERROR_PAGELOCK',
            20011: 'DRV_ERROR_PAGE_UNLOCK',
            20012: 'DRV_ERROR_BOARDTEST',
            20013: 'DRV_ERROR_ACK',
            20014: 'DRV_ERROR_UP_FIFO',
            20015: 'DRV_ERROR_PATTERN',
            20017: 'DRV_ACQUISITION_ERRORS',
            20018: 'DRV_ACQ_BUFFER',
            20019: 'DRV_ACQ_DOWNFIFO_FULL',
            20020: 'DRV_PROC_UNKNOWN_INSTRUCTION',
            20021: 'DRV_ILLEGAL_OP_CODE',
            20022: 'DRV_KINETIC_TIME_NOT_MET',
            20023: 'DRV_ACCUM_TIME_NOT_MET',
            20024: 'DRV_NO_NEW_DATA',
            20026: 'DRV_SPOOLERROR',
            20033: 'DRV_TEMPERATURE_CODES',
            20034: 'DRV_TEMPERATURE_OFF',
            20035: 'DRV_TEMPERATURE_NOT_STABILIZED',
            20036: 'DRV_TEMPERATURE_STABILIZED',
            20037: 'DRV_TEMPERATURE_NOT_REACHED',
            20038: 'DRV_TEMPERATURE_OUT_RANGE',
            20039: 'DRV_TEMPERATURE_NOT_SUPPORTED',
            20040: 'DRV_TEMPERATURE_DRIFT',
            20049: 'DRV_GENERAL_ERRORS',
            20050: 'DRV_INVALID_AUX',
            20051: 'DRV_COF_NOTLOADED',
            20052: 'DRV_FPGAPROG',
            20053: 'DRV_FLEXERROR',
            20054: 'DRV_GPIBERROR',
            20064: 'DRV_DATATYPE',
            20065: 'DRV_DRIVER_ERRORS',
            20066: 'DRV_P1INVALID',
            20067: 'DRV_P2INVALID',
            20068: 'DRV_P3INVALID',
            20069: 'DRV_P4INVALID',
            20070: 'DRV_INIERROR',
            20071: 'DRV_COFERROR',
            20072: 'DRV_ACQUIRING',
            20073: 'DRV_IDLE',
            20074: 'DRV_TEMPCYCLE',
            20075: 'DRV_NOT_INITIALIZED',
            20076: 'DRV_P5INVALID',
            20077: 'DRV_P6INVALID',
            20078: 'DRV_INVALID_MODE',
            20079: 'DRV_INVALID_FILTER',
            20080: 'DRV_I2CERRORS',
            20081: 'DRV_DRV_I2CDEVNOTFOUND',
            20082: 'DRV_I2CTIMEOUT',
            20083: 'DRV_P7INVALID',
            20089: 'DRV_USBERROR',
            20090: 'DRV_IOCERROR',
            20091: 'DRV_NOT_SUPPORTED'}
        ret = values.get(value, 'NotRegistered_'+str(value))
        return ret 
            
            




# a = AndorEMCCD()
# a.initialize()
# print a.getImage().shape










































