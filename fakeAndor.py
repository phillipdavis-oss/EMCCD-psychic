# -*- coding: utf-8 -*-
"""
Created on Sat Feb 14 19:00:33 2015

@author: Home
"""

import numpy as np
import time
import logging
import scipy.signal as sps
log = logging.getLogger("Andor")
# import interactivePG as pg


class myCallable(object):
    ''' Need a class which is callable, but also
        need it to have the argtypes and restype 
        parameters to match the calls made setting up the CCD. '''
    def __init__(self, func=None, st = '', retWeights = ()):
        self.argtypes = []
        self.restype = None
        self.st = st
        self.func = func
        # ((retchance1, retchance2, retchance3... ),
        #  (retval1,    retval2,    retval3))
        self.retWeights = retWeights
        
    def __call__(self, *args):
        log.debug("{}, {}".format(' '*10+self.st, args))
        self.func(args)
        ret = 20002
        # if not np.random.randint(5):
        #     ret = 20004
        if self.retWeights:
            ranges = np.cumsum(self.retWeights[0])
            rando = np.random.randint(ranges[-1])
            return self.retWeights[1][
                # Grab the first one where
                # it crosses over
                np.argwhere(rando<ranges)[0][0]
            ]
        """
        if self.st == "GetTemperature":
            n = np.random.randint(20)
            if n == 1:
                ret = 20036 # temp stabilized
            else:
                ret = 20037
        elif self.st == "Initialize":
            ret = -1
        elif self.st == 'InitializeMissingDLL':
            ret = -2
        """

        return ret

class fAndorEMCCD(object):
    _image = [1, 1, 1, 400, 1, 1600]
    exposure = 0.5
    def __init__(self):
        self.AbortAcquisition = myCallable(self.__voidReturn, 'AbortAcquisition')
        self.CancelWait = myCallable(self.__voidReturn, 'CancelWait')
        self.CoolerON = myCallable(self.__voidReturn, 'CoolerON')
        self.CoolerOFF = myCallable(self.__voidReturn, 'CoolerOFF')
        self.GetAcquiredData = myCallable(self.__getData, 'GetAcquiredData')
        self.GetAcquisitionTimings = myCallable(self.__getTimings, 'GetAcquisitionTimings')
        self.GetCapabilities = myCallable(self.__voidReturn, 'GetCapabilities')
        self.GetDetector = myCallable(self.__getDet, 'GetDetector')
        self.GetHSSpeed = myCallable(self.__getHSS, 'GetHSSpeed')
        self.GetKeepCleanTime = myCallable(self.__getKeepClean, 'GetKeepCleanTime')
        self.GetMostRecentImage = myCallable(self.__voidReturn, 'GetMostRecentImage')
        self.GetNumberADChannels = myCallable(self.__getNum, 'GetNumberADChannels')
        self.GetNumberHSSpeeds = myCallable(self.__getNum, 'GetNumberHSSpeeds')
        self.GetNumberVSSpeeds = myCallable(self.__getNum, 'GetNumberVSSpeeds')
        self.GetReadOutTime = myCallable(self.__getReadout, 'GetReadOutTime')
        self.GetStatus = myCallable(self.__getNum, 'GetStatus')
        self.GetTemperature = myCallable(self.__getNum, 'GetTemperature', ((1, 20), (20036, 20037)))
        self.GetVSSpeed = myCallable(self.__getHSS, 'GetVSSpeed')
        self.Initialize = myCallable(self.__voidReturn, 'Initialize', ((1, ), (-1,)))
        self.PrepareAcquisition = myCallable(self.__voidReturn, 'PrepAcq')
        self.SetAcquisitionMode = myCallable(self.__voidReturn, 'SetAcqMode')
        self.SetADChannel = myCallable(self.__voidReturn, 'SetADChannel')
        self.SetCoolerMode = myCallable(self.__voidReturn, 'SetCoolerMode')
        self.SetEMCCDGain = myCallable(self.__voidReturn, 'SetEMCCDGain')
        self.SetExposureTime = myCallable(self.__setExp, 'SetExposureTime')
        self.SetGain = myCallable(self.__voidReturn, 'SetGain')
        self.SetHSSpeed = myCallable(self.__voidReturn, 'SetHSSpeed')
        self.SetImage = myCallable(self.__setImage, 'SetImage')
        self.SetReadMode = myCallable(self.__voidReturn, 'SetReadout')
        self.SetShutter = myCallable(self.__voidReturn, 'SetShutter')
        self.SetShutterEx = myCallable(self.__voidReturn, 'SetShutterEx')
        self.SetTemperature = myCallable(self.__voidReturn, 'SetTemp')
        self.SetTriggerMode = myCallable(self.__voidReturn, 'SetTriggerMode')
        self.SetVSSpeed = myCallable(self.__voidReturn, 'SetVSSpeed')
        self.ShutDown = myCallable(self.__voidReturn, "SHUT 'ER DOWN")
        self.StartAcquisition = myCallable(self.__voidReturn, 'Start Acquisition')
        self.WaitForAcquisition = myCallable(self.__wait, 'WaitForAqcuisition')

        
    def __voidReturn(self, *args):
        # int hbin: number of pixels to bin horizontally.
        # int vbin: number of pixels to bin vertically.
        # int hstart: Start column (inclusive).
        # int hend: End column (inclusive).
        # int vstart: Start row (inclusive).
        # int vend: End row (inclusive).
        pass

    def __setImage(self, *args):
        self._image = list(args[0])

    def __getData(self, *args):
        hbin, vbin, hstart, hend, vst, ven = tuple(self._image)
        bg = np.random.normal(297, 6, (400,1600))
        if not np.random.randint(3):
            ret = bg
        else:
            cosmicMask = np.zeros_like(bg)
            cosmicLocx = np.random.randint(0,400, size=(5,))
            cosmicLocy = np.random.randint(0,1600, size=(5,))
            cosmicMask[cosmicLocx, cosmicLocy] = np.random.randint(20000, 60000, size=(5,))

            a = sps.windows.gaussian(5, 1)[None,:]
            b = sps.windows.gaussian(25, 5)[:,None]
            sbKernal = a*b
            # space 50px apart
            sbMask = np.zeros_like(bg)

            x = np.exp(1./8*np.arange(32))+1
            for ii, sbLoc in enumerate(np.arange(41, 1600, 50)):
                sbMask[220:245, sbLoc-2:sbLoc+3] = sbKernal * 800 * x[ii]

            ret = bg + cosmicMask + sbMask
            # print ret[vst:ven, :].shape
            # print (vbin, (ven-vst+1)/vbin, ret.shape[1])
        ret = ret[vst-1:ven, :].reshape((vbin, (ven-vst+1)//vbin, ret.shape[1])).sum(axis=0)
        ret = np.fliplr(ret)
        ret = ret.astype('int')
        ret = ret.ravel()
        arr = args[0][0]
        for i in range(args[0][1]):
            arr[i] = ret[i]



            
    def __getDet(self, *args):
        x = args[0][0]
        y = args[0][1]
        x.value = 1600
        y.value = 400
        
    def __getHSS(self, *args):
        # print args
        x = args[0][-1]
        x.value = np.random.randint(100)
        x.value = 0.2 + args[0][-2] + len(args[0])*5
    
    def __getNum(self, *args):
        x = args[0][-1]
        x.value = np.random.randint(3, 5)

    def __readoutTime(self):
        """Pretend to read the chip out at 1 MHz, so the fake camera's
        timings scale with the ROI/binning the way a real one's do."""
        hbin, vbin, hstart, hend, vst, ven = tuple(self._image)
        return ((hend - hstart + 1) // hbin) * ((ven - vst + 1) // vbin) * 1e-6

    def __getTimings(self, *args):
        exposure, accumulate, kinetic = args[0]
        exposure.value = self.exposure
        accumulate.value = self.exposure + self.__readoutTime()
        kinetic.value = accumulate.value

    def __getReadout(self, *args):
        args[0][-1].value = self.__readoutTime()

    def __getKeepClean(self, *args):
        args[0][-1].value = 1e-3

    def __cancelWait(self, *args):
        self.WaitForAcquisition.retWeights = ((1,), (20024,))
    def __wait(self, *args):
        # Wait a random amount of time to simulate it
        self.WaitForAcquisition.retWeights = ((1,), (20002,))
        print("Sleeping for: {}".format(self.exposure))
        time.sleep(self.exposure)

    def __setExp(self, val):
        self.exposure = val[0]
    
    

    
        



# a = fAndorEMCCD()



















































