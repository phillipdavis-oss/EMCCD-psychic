# -*- coding: utf-8 -*-
"""
Created on Mon Jan 19 14:01:23 2015

@author: dreadnought

"Brevity required, prurience preferred"
"""

import os, errno
import copy
import functools
import json
import numpy as np
# what the hell is this?
# hangs on my mac at this import line
# no idea what the fuck is going on here.
# import matplotlib.pylab as plt
# from . import cosmics_hsg as cosmics
import cosmics_hsg as cosmics
import scipy.ndimage as ndimage
import pyqtgraph as pg
from UIs.ImageViewWithPlotItemContainer import ImageViewWithPlotItemContainer
import logging


log = logging.getLogger("EMCCD")


class ConsecutiveImageAnalyzer(object):
    def __init__(self):
        """
        This class will function to hold and control
        all things necessary for performing statistical
        metrics for consecutive, identical situation
        CCD exposures. Namely, this is the raw
        camera image, and the normalization factor
        which may change between images (i.e. FEL pulses)
        :return:
        """
        self._rawImages = []
        self._cleanImages = None
        self._normFactors = []
        # how memory inefficient is it to
        # keep a cache of it?
        self._stackedImages = None

        # parameters for the crr algorithm
        self.crrParams = {
            "ratio": 1.0,
            "noisecoeff":5.0
        }

        # Set to True to to not normalize the
        # images when doing crr
        self.ignoreNormFactors = False

    def addImage(self, image, normFactor = None):
        if isinstance(image, EMCCD_image):
            if self._rawImages and image.raw_array.shape != self._rawImages[0].shape:
                raise ValueError("Input dimensions must match!\n\t got: {}, want: {}".format(
                    image.raw_array.shape, self._rawImages[0].shape
                ))
            self._rawImages.append(image.raw_array)
            if normFactor is None:
                felp = image.equipment_dict.get("fel_pulses", 0)
                # print "from eqp dict", felp
                if felp == 0: felp = 1
            else:
                felp = normFactor
            # print "Added an image, norm factor", felp
            self._normFactors.append(felp)
        else:
            if self._rawImages and image.shape != self._rawImages[0].shape:
                raise ValueError("Input dimensions must match!\n\t got: {}, want: {}".format(
                    image.raw_array.shape, self._rawImages[0].shape
                ))
            if normFactor is None: normFactor = 1
            self._rawImages.append(image)
            self._normFactors.append(normFactor)

        self._stackedImages = None

    def removeImageByIdx(self, index):
        try:
            self._rawImages.pop(index)
            self._normFactors.pop(index)
            self._stackedImages = None
        except Exception as e:
            log.warning("Error trying to pop the images, {}".format(e))

    def removeCosmics(self, ratio = 0.07, noisecoeff = 3.0, debug = False):
        if self._stackedImages is None:
            self.getImages()
        d = np.array(self._stackedImages).astype(float)

        normFactors = np.array(self._normFactors)
        if not self.ignoreNormFactors:
            try:
                d /= normFactors[:,None, None]
            except:
                log.exception("Error normalizing")
                # print("error here")
                # print(type(d), d)
                # print(type(normFactors), normFactors)
                # raise


        med = np.median(d, axis=0)
        # estimate the noise by taking the std along the first
        # 100px of each row, for each vertical pixel.
        # Then just average those, as the noise should be roughly
        # consant, and that will hopefully smear out the presence of
        # sidebands or cosmics within the first 100px?

        signoise = np.std(d[:,:,:100], axis=2).mean()
        cutoff = med * ratio + noisecoeff * signoise

        if debug:
            try:
                if d.shape[1]>10:
                    debug = False
                    raise RuntimeError("Sorry, can't debug with this large"
                                       "an image, it causes things to break")
                print("median shape", med.shape)
                cutoff = med * ratio + noisecoeff * np.std(med[:,:100])
                print("cutoff shape", cutoff.shape)

                winlist = []

                vw = ImageViewWithPlotItemContainer(view=pg.PlotItem())
                vw.view.setAspectLocked(False)
                vw.setImage(d.copy())
                vw.setWindowTitle("Raw Image")
                vw.roi.setSize((d.shape[2], d.shape[1]))
                vw.roi.translatable = False
                vw.ui.roiPlot.plotItem.addLegend()
                for ii in range(0, d.shape[0]):
                    for kk in range(0, d.shape[1]):
                        vw.ui.roiPlot.plot(d[ii,kk], pen=pg.mkPen((ii, d.shape[0]), style=kk+1), name=ii)
                # vw.updateImage()

                vw.show()
                vw.ui.roiBtn.setChecked(True)
                vw.ui.roiBtn.clicked.emit(True)
                winlist.append(vw)
                vw = ImageViewWithPlotItemContainer(view=pg.PlotItem())
                vw.view.setAspectLocked(False)
                # vw.setImage(d.reshape(d.shape[2], d.shape[1], d.shape[0]))
                vw.setImage(med)
                vw.setWindowTitle("Median Image")
                vw.roi.setSize((med.shape[1], med.shape[0]))
                vw.roi.translatable = False
                vw.ui.roiPlot.plotItem.addLegend()
                for ii in range(0, med.shape[0]):
                        vw.ui.roiPlot.plot(med[ii], pen=pg.mkPen(style=ii+1), name=ii)
                # vw.updateImage()

                vw.show()
                vw.ui.roiBtn.setChecked(True)
                vw.ui.roiBtn.clicked.emit(True)
                winlist.append(vw)


                vw = ImageViewWithPlotItemContainer(view=pg.PlotItem())
                vw.view.setAspectLocked(False)
                # vw.setImage(d.reshape(d.shape[2], d.shape[1], d.shape[0]))
                vw.setImage(d-med)
                vw.setWindowTitle("d-m")
                vw.roi.setSize((med.shape[1], med.shape[0]))
                vw.roi.translatable = False
                vw.ui.roiPlot.plotItem.addLegend()
                for ii in range(0, d.shape[0]):
                    for kk in range(0, d.shape[1]):
                        vw.ui.roiPlot.plot(d[ii,kk]-med[kk], pen=pg.mkPen((ii, d.shape[0]), style=kk+1), name=ii)
                for ii in range(0, med.shape[0]):
                        vw.ui.roiPlot.plot(cutoff[ii], pen=pg.mkPen(style=ii+1), name=ii)
                # vw.updateImage()

                vw.show()
                vw.ui.roiBtn.setChecked(True)
                vw.ui.roiBtn.clicked.emit(True)
                winlist.append(vw)


                vw = ImageViewWithPlotItemContainer(view=pg.PlotItem())
                vw.view.setAspectLocked(False)
                # vw.setImage(d.reshape(d.shape[2], d.shape[1], d.shape[0]))
                vw.setImage((d-med)>cutoff[None,:,:])
                vw.setWindowTitle("Cosmics?")
                vw.roi.setSize((d.shape[2], d.shape[1]))
                vw.roi.translatable = False
                vw.ui.roiPlot.plotItem.addLegend()
                for ii in range(0, d.shape[0]):
                    for kk in range(0, d.shape[1]):
                        vw.ui.roiPlot.plot(((d-med)>cutoff[None,:,:])[ii,kk], pen=pg.mkPen((ii, d.shape[0]), style=kk+1), name=ii)
                # vw.updateImage()

                vw.show()
                vw.ui.roiBtn.setChecked(True)
                vw.ui.roiBtn.clicked.emit(True)
                winlist.append(vw)

            except:
                log.exception("this failed")



        badPix = np.where((d-med)>cutoff[None,:,:])
        d[badPix] = np.nan
        if not self.ignoreNormFactors:
            d *= normFactors[:,None, None]

        # To be comprable to background
        std = np.nanstd(d, axis=0)

        # if not self.ignoreNormFactors:
        #     d /= normFactors[:,None, None]

        # d[badPix] = np.nanmean(d[:, badPix[1], badPix[2]], axis=0)
        # if not self.ignoreNormFactors:
        #     d *= normFactors[:,None, None]

        # replace the cosmics
        d[badPix] = np.nanmean(d[:, badPix[1], badPix[2]], axis=0)
        self._cleanImages = np.array(d)

        if debug:

                vw = ImageViewWithPlotItemContainer(view=pg.PlotItem())
                vw.view.setAspectLocked(False)
                vw.setImage(self._cleanImages.copy())
                vw.setWindowTitle("Clean Image")
                vw.roi.setSize((d.shape[2], d.shape[1]))
                vw.roi.translatable = False
                vw.ui.roiPlot.plotItem.addLegend()
                for ii in range(0, d.shape[0]):
                    for kk in range(0, d.shape[1]):
                        vw.ui.roiPlot.plot(d[ii,kk], pen=pg.mkPen((ii, d.shape[0]), style=kk+1), name=ii)
                # vw.updateImage()

                vw.show()
                vw.ui.roiBtn.setChecked(True)
                vw.ui.roiBtn.clicked.emit(True)
                winlist.append(vw)
                self.winList = winlist




        d = np.nanmean(d, axis=0).astype(int)

        return d, std

    def subtractImage(self, other):
        """

        :param other:
        :type other: EMCCD_image
        :return:
        """
        if other.std_array is not None:
            back = other.clean_array
            sigb = other.std_array
        else:
            back = np.mean(other.imageSequence.getImages().astype(float), axis=0)
            sigb = np.std(other.imageSequence.getImages(), axis=0)
        normfact = np.array(self._normFactors)

        img = np.array(self.getImages()).astype(float)
        sigim = np.std(img, axis=0)
        sigT = np.sqrt(sigb**2 + sigim**2)

        img -= back[None, :, :]
        if not self.ignoreNormFactors:
            img /= normfact[:, None, None]
            sigT /= np.sum(normfact)

        sigpost = np.std(img, axis=0)
        sigpost /= np.sqrt(img.shape[0])
        sigT /= np.sqrt(img.shape[0])

        return np.mean(img, axis=0), sigpost, sigT

    def clearImages(self):
        self._rawImages = []
        self._cleanImages = None
        self._normFactors = []
        self._stackedImages = None

    def getImages(self):
        # prefer returning the clean stuff, I think this is
        # what you'd always want
        if self._cleanImages is not None:
            return self._cleanImages.copy()
        if self._stackedImages is not None:
            return self._stackedImages
        elif not self._rawImages:
            return np.zeros((10, 10, 10)) - 1
        self._stackedImages = np.array(self._rawImages[0])[None,:,:]

        if len(self._rawImages)==1:
            return self._stackedImages

        for newImage in self._rawImages[1:]:
            self._stackedImages = np.concatenate(
                (self._stackedImages, newImage[None,:,:]), axis=0
            )
        return self._stackedImages

    def numImages(self):
        return len(self._rawImages)

def loadImageFile(fname, cls = None):
    """
    Given the filename of an image file, will open it up,
    get the equipment dict and data out of it. If cls is
    not None, will return an instantiated image data class
    of the data. Otherwise, will return the data/equip dict
    :param fname: The filename of the file to be loaded
    :param cls: Class of the object to be returned
    :return: An instantiated class of the filename
    :rtype: cls
    """
    with open(fname) as fh:
        param_str = ''
        line = fh.readline()
        while line[0] == '#':
            param_str += line[1:]
            line = fh.readline()
            # new = fh.readline()
            # initial = new[0]
            # param_str += new[1:]
        parameters = json.loads(param_str)
    data = np.genfromtxt(fname, delimiter=',')
    if cls is None:
        return data, parameters
    else:
        obj = cls(data,
                  file_name = parameters.get('filename', ''),
                  file_no = parameters.get('fileno', ''),
                  description = parameters.get('comments', ''),
                  equipment_dict = parameters.copy()
                  )
        obj.clean_array = obj.raw_array # it's been saved so it's been cleaned
        obj.equipment_dict["background_file"] = parameters["background_file"]

        return obj

class EMCCD_image(object):
    origin_import = '\nWavelength,Signal\nnm,arb. u.'
    
    def __init__(self, raw_array=None, file_name='', file_no=None, description='', equipment_dict=None):
        """
        This init is to work with the most basic images with no specialiation
        for HSG or PL or absorbance data.  Feels like we should have something
        more general than those.
        
        raw_array = the CCD image with the pertinent data
        bg_array = the CCD image with the pertinent backgroud data
        description = string that contains a brief description of the file
        equipment_dict = dictionary that contains the important settings of the
                         equipment:
                             CCD_temperature = temp of CCD chip
                             exposure = exposure time
                             gain = EM gaine
                             y_min = lower boundary of ROI
                             y_max = upper boundary of ROI
                             grating = spectrometer grating
                             center_lambda = spectrometer wavelength setting
                             slits = width of slits in microns
                             dark_region (maybe not that useful if can look at y_max + n)
							 series = name for series
        """
        # These default to None, not to [] / {}: a mutable default is shared
        # by every call, and this class writes into equipment_dict below
        # ("background_file"), so images built without an explicit dict would
        # otherwise all share one.
        if raw_array is None:
            raw_array = []
        if equipment_dict is None:
            equipment_dict = {}

        self.raw_array = np.array(raw_array)
        self.raw_shape = self.raw_array.shape
        self.file_name = file_name
        self.saveFileName = '' # where were you actually saved?
        self.file_no = file_no
        self.description = description
        self.equipment_dict = equipment_dict
        if self.equipment_dict and self.equipment_dict.get('y_max', 0) - self.equipment_dict.get('y_min', 0) > int(self.raw_shape[0]):
            log.warning("y_min and y_max were set incorrectly")
            self.equipment_dict['y_max'] = int(self.raw_shape[0])
            self.equipment_dict['y_min'] = 0
        self.clean_array = None
        self.std_array = None # for holding the std of pixels
        self.spectrum = None
        self.equipment_dict["background_file"] = ''

        self.imageSequence = ConsecutiveImageAnalyzer()

        self.isSequence = False
        # keep a reference to the full file name of the
        # spectrum file which is saved
        # (used by the gui to load the file and fit the
        # sb to find frequencies)
        self.spectrumFileName = 'NotSet'

    def __str__(self):
        '''
        This will print the description of the file.  I'm not sure what else
        would be useful at this time.
        '''
        return self.description
    
    def __add__(self, other):
        '''
        This will copy the first element in the sum, then add the clean_arrays
        from self and other to each other.  It can also currently add an int or
        float to the clean_array.  I'm not sure if that kind of addition is 
        useful.
        
        The center_lambda check needs to be changed to match how that 
        dictionary entry works.  It could get ugly without double checking.
        '''
        if self.clean_array is None:
            log.error("Unable to add: First array not cleaned")
            raise Exception('Source: EMCCD_image.__add__\nThe first array has not been cleaned yet')
        ret = copy.deepcopy(self)
        
        # Add a constant offset to the data
        if isinstance(other, (int, float, np.integer, np.floating)):
            ret.clean_array = self.clean_array + other
        
        # or add the two clean_arrays together
        else:
            if np.isclose(ret.equipment_dict['center_lambda'], 
                          other.equipment_dict['center_lambda']):
                ret.clean_array = self.clean_array + other.clean_array
            else:
                print("self:{}, ret:{}, other:{}".format(
                    self.equipment_dict['center_lambda'],
                    ret.equipment_dict['center_lambda'],
                    other.equipment_dict['center_lambda']
                ))
                # raise Exception('Source: EMCCD_image.__add__\nThese are not from the same grating settings')
                log.error("Unable to add, data not from same grating settings")
        return ret

    def __sub__(self, other):
        '''
        This subtracts constants or other data sets between self.hsg_data.  I 
        think it even keeps track of what data sets are in the file and how 
        they got there.  
        
        The center_lambda check needs to be changed to match how that 
        dictionary entry works.  It could get ugly without double checking.
        '''
        if self.clean_array is None:
            raise Exception('Source: EMCCD_image.__sub__\nThe first array has not been cleaned yet')
        ret = copy.deepcopy(self)
        
        if isinstance(other, (int, float, np.integer, np.floating)):
            ret.clean_array = self.clean_array - other
        else:
            if np.isclose(ret.equipment_dict['center_lambda'], 
                          other.equipment_dict['center_lambda']):
                ret.clean_array = self.clean_array - other.clean_array

            else:
                raise Exception('Source: EMCCD_image.__sub__\nThese are not from the same grating settings')
        return ret
        
    def __getslice__(self, *args):
        print('getslice ', args)
        #Simply pass the slice along to the data
        return self.spectrum[args[0]:args[1]]
        
    def __iter__(self):
        for i in range(len(self.spectrum)):
            yield self.spectrum[i]
        return
    
    def set_ylimits(self, y_min, y_max):
        '''
        This changes y_min and y_max
        '''
        self.equipment_dict['y_min'] = y_min
        self.equipment_dict['y_max'] = y_max
    
    def cosmic_ray_removal(self, mygain=10, myreadnoise=0.2, mysigclip=5.0, mysigfrac=0.01, myobjlim=3.0, myverbose=True):
        '''
        This is a single operation of cosmic ray removal.

        If EMCCD isn't cold enough, the hot pixels wil be removed as well.  I 
        don't know if this is a bad thing?  I think it should just be a thing
        that doesn't happen.
        
        mygain = the gain.  This does not seem to actually be the EM gain of 
                 the EMCCD
        myreadnoise = Level (imprecise!) of read noise used in the statistical
                      model built to recognize cosmic arrays.  It's a function
                      of gain on our CCD, I believe.  Dark current should be 
                      separate, technically, but it would look like noise 
                      because of shot noise and crap
        mysigclip = I forget
        mysicfrac = I forget
        myobjlim = I forget
        myverbose = Tells hsg_cosmics to print out what it's doing
        
        returns a clean my_array
        '''
        
#        self.clean_array = self.raw_array
#        return
        image_removal = cosmics.cosmicsimage(self.raw_array, gain=mygain, # I don't understand gain
                                             readnoise=myreadnoise, 
                                             sigclip=mysigclip, 
                                             sigfrac=mysigfrac, 
                                             objlim=myobjlim)
        image_removal.run(maxiter=4)
        self.clean_array = image_removal.cleanarray
    
    def make_spectrum(self, std = None):
        '''
        Integrates over vertical axis of the cleaned image
        
        I'm not exactly sure y_min and y_max are counting from the same side as
        in the UI.
        '''
        if self.std_array is None:
            try:
                self.spectrum = self.clean_array[self.equipment_dict['y_min']:self.equipment_dict['y_max'],:].sum(axis=0)
            except:
                self.spectrum = self.raw_array[self.equipment_dict['y_min']:self.equipment_dict['y_max'],:].sum(axis=0)
            wavelengths = gen_wavelengths(self.equipment_dict['center_lambda'],
                                          self.equipment_dict['grating'],
                                          self.spectrum.shape[0])
            self.spectrum = np.vstack((wavelengths, self.spectrum)).T
        else:
            self.spectrum = self.clean_array[self.equipment_dict['y_min']:self.equipment_dict['y_max'],:].sum(axis=0)
            spec_std = np.mean(self.std_array[self.equipment_dict['y_min']:self.equipment_dict['y_max'],:], axis=0)
            wavelengths = gen_wavelengths(self.equipment_dict['center_lambda'],
                                          self.equipment_dict['grating'],
                                          self.spectrum.shape[0])
            self.spectrum = np.vstack((wavelengths, self.spectrum, spec_std)).T


        
    def inspect_dark_regions(self):
        '''
        This will look at a dark area, I'm not quite sure how yet, to make sure
        the mean is set to zero.  It will also measure the standard deviation 
        of the noise for use later.
        '''
        dark_region = self.clean_array[0,:] # This is a total kludge
        self.dark_mean = np.mean(dark_region)
        self.std_dev = np.std(dark_region)
        # print "Base line is ", self.dark_mean
        # print "Standard deviation is ", self.std_dev
        height = self.equipment_dict['y_max'] - self.equipment_dict['y_min']
        if height == self.clean_array.shape[0]:
            log.warn("Integrating full image, cannot do dark count subtraction!")
            return
        self.spectrum[:,1] = self.spectrum[:, 1] - self.dark_mean*height
        self.clean_array -= self.dark_mean
    
    def save_spectrum(self, folder_str='Spectrum files', prefix=None, postfix = '', origin_header = None):
        '''
        Saves the general spectrum.  Unsure if we need it, but, again, seems
        useful for novel, basic stuff.
        '''

        # take the dark_region to be the std of the bottom row
        # data shape in np array is not the same as on the pyqtgraph images
        # The 0th index corresponds to the lowest row as seen in
        # the live image.
        self.equipment_dict["dark_region"] = np.std(
            self.clean_array[0,:]
        )

        condensedFEL = {}
        try:
            if self.isSequence and "fieldStrength" in self.equipment_dict:
                keys = ["fieldStrength", "cdRatios",
                        "fieldInt", "fpTime",
                        "pyroVoltage", "pulseDuration",
                        "pulseEnergies"]
                # keys = [k for k in keys if k in self.equipment_dict]
                for k in keys:
                    try:
                        condensedFEL[k] = {
                            "mean": np.mean([ii["mean"] for ii in self.equipment_dict[k]]),
                            "std": np.mean([ii["std"] for ii in self.equipment_dict[k]])
                        }
                    except KeyError:
                        pass # fpTime/cdRatios breaks for Cavity Dumping differencs
                condensedFEL["fel_pulses"] = int(np.sum(self.equipment_dict["fel_pulses"]))
        except Exception as e:
            log.exception("Something fucked up trying to condense FEL settings")



        eq_dict = self.equipment_dict.copy()
        eq_dict.update({"comments":self.description})
        eq_dict.update(condensedFEL)


        equipment_str = json.dumps(eq_dict, separators=(',', ': '),
                      sort_keys=True, indent=4, default=lambda x:"Thisonefuckedup {}".format(type(x)) )
        if origin_header is None:
            origin_import = self.origin_import
        else:
            origin_import = origin_header

        filename = self.getFileName(prefix)
        filename += postfix

        num_lines = equipment_str.count('\n')  # Make the number of lines constant so importing is easier
        for num in range(99 - num_lines): equipment_str += '\n'

        filename += "_spectrum.txt"
        my_header = '#' + equipment_str.replace('\n', '\n#') + origin_import
        if folder_str==".":
            self.spectrumFileName=filename
        else:
            self.spectrumFileName = os.path.join(folder_str, 'Spectra', self.file_name, filename)


        np.savetxt(self.spectrumFileName, self.spectrum,
                   delimiter=',', header=my_header, comments = '', fmt='%f')
    
    def save_images(self, folder_str='Raw files', prefix=None, data = None,
                    fmt = '%d', postfix = ''):
        '''
        Saves the raw_array, not the cleaned one.  Cleaning isn't that hard, 
        and how we do it could change in the future.
        
        This really depends on how the folders are initialized by the UI.  Will
        they already exist by the time we get to saving images, or do they need
        to be created on the fly?
        
        Also, I'm pretty sure self.raw_array is still ints?
        '''
        eq_dict = self.equipment_dict.copy()
        eq_dict.update({"comments":self.description,
                        "filename": self.file_name,
                        "fileno": self.file_no,
                        "noImages": self.imageSequence.numImages()})


        filename = self.getFileName(prefix)
        filename += postfix + '.txt'

        if data is None:
            data = self.raw_array
        eq_dict["dark_region"] = np.std(
            data[0,:]
        )


        try:
            equipment_str = json.dumps(eq_dict, separators=(',', ': '),
                          sort_keys=True, indent=4 )
        except Exception as e:
            print("Exception jsoning")
            print(e)
            print(eq_dict)


        my_header = '#' + equipment_str.replace('\n', '\n#')

        self.saveFileName = filename
        np.savetxt(os.path.join(folder_str, "Images", filename), data,
               delimiter=',', header=my_header, comments = '', fmt=fmt)
        # print "Saved image\nDirectory: {}".format(
        #     os.path.join(folder_str, "Images", filename)
        # )

    def getFileName(self, prefix=None):
        """
        Convenience function to get the name used for saving.
        """
        # All the data will end up doig the same thing,
        # only difference is the preffix to the name (?)
        # which can also be set specifically with the function call
        if prefix is None:
            # Get the name of the class calling it
            name = type(self).__name__.lower()
            if "hsg" in name:
                filename = "hsg_"
            elif "pl" in name:
                filename = "pl_"
            elif "abs" in name:
                filename = "absRaw_"
            else:
                filename = ""
        else:
            filename = str(prefix)


        filename += self.file_name + self.file_no
        return filename

    def setAsSequence(self):
        """
        This function is called by the expwidget when this object
        becomes a sequence image. Sets things up to be ready to take multiple
        images. Updates things such as FEL pulses/stats in the equipment dict
        to be lists to append to.
        :return:
        """ 
        self.imageSequence.clearImages()
        self.imageSequence.addImage(self)
        self.isSequence = True
        self.equipment_dict["images_in_sequence"] = [self.saveFileName]
        if "fieldStrength" in self.equipment_dict:
            self.equipment_dict["fieldStrength"] = [
                self.equipment_dict["fieldStrength"]
            ]

            self.equipment_dict["fieldInt"] = [
                self.equipment_dict["fieldInt"]
            ]

            self.equipment_dict["fel_pulses"] = [
                self.equipment_dict["fel_pulses"]
            ]



            self.equipment_dict["pulseEnergies"] = [
                self.equipment_dict["pulseEnergies"]
            ]
            self.equipment_dict["pyroVoltage"] = [
                self.equipment_dict["pyroVoltage"]
            ]
            if "fpTime" in self.equipment_dict:
                self.equipment_dict["fpTime"] = [
                    self.equipment_dict["fpTime"]
                ]
                self.equipment_dict["cdRatios"] = [
                    self.equipment_dict["cdRatios"]
                ]
            else:
                self.equipment_dict["pulseDuration"] = [
                    self.equipment_dict["pulseDuration"]
                ]


    def addNewImage(self, newImage):
        """
        This function should be called by an object
        which serves to act as a collection of multiple images.

        This will collect the FEL changes (pulses, strength, etc)
        :param newImage:
        :type newImage: EMCCD_image
        :return:
        """
        if "fieldStrength" in self.equipment_dict:
            self.equipment_dict["fieldStrength"].append(
                newImage.equipment_dict["fieldStrength"]
            )

            self.equipment_dict["fieldInt"].append(
                newImage.equipment_dict["fieldInt"]
            )

            self.equipment_dict["fel_pulses"].append(
                newImage.equipment_dict["fel_pulses"]
            )

            self.equipment_dict["pulseEnergies"].append(
                newImage.equipment_dict["pulseEnergies"]
            )
            self.equipment_dict["pyroVoltage"].append(
                newImage.equipment_dict["pyroVoltage"]
            )
            if "fpTime" in self.equipment_dict:
                self.equipment_dict["fpTime"].append(
                    newImage.equipment_dict["fpTime"]
                )
                self.equipment_dict["cdRatios"].append(
                    newImage.equipment_dict["cdRatios"]
                )
            else:
                self.equipment_dict["pulseDuration"].append(
                    newImage.equipment_dict["pulseDuration"]
                )
        self.imageSequence.addImage(newImage)
        self.equipment_dict["images_in_sequence"].append(newImage.saveFileName)

    def removeImageBySequence(self, index):
        try:
            if "fieldStrength" in self.equipment_dict:
                self.equipment_dict["fieldStrength"].pop(index)
                self.equipment_dict["fieldInt"].pop(index)
                self.equipment_dict["fel_pulses"].pop(index)
                self.equipment_dict["pyroVoltage"].pop(index)
                if "fpTime" in self.equipment_dict:
                    self.equipment_dict["fpTime"].pop(index)
                    self.equipment_dict["cdRatios"].pop(index)
                else:
                    self.equipment_dict["pulseDuration"].pop(index)
            self.imageSequence.removeImageByIdx(index)
        except Exception as e:
            log.warning("Exception trying to remove an image")




class HSG_image(EMCCD_image):
    '''
    This subclass will specialize in HSG initializing and saving, which mostly
    has to do with what the header in the file is at this point.  
    '''
    pass

class HSG_FVB_image(HSG_image):
    def __init__(self, raw_array=None, file_name='', file_no=None, description='', equipment_dict=None):
        super(HSG_FVB_image, self).__init__(raw_array, file_name, file_no, description, equipment_dict)
        self.isSeries = False

    def cosmic_ray_removal(self, offset = 0, medianRatio = 1, noiseCoeff = 5,
                           debug = False):
        """
        Remove cosmic rays from the raw_array when it is a sequence
        of consecutive exposures.
        :param offset: baseline to add to raw_array.
               Not used, but here if it's needed in the future
        :param medianRatio: Multiplier to the median when deciding a cutoff
        :param noiseCoeff: Multiplier to the noise on the median
                    May need changing for noisy data
        :param debug: pop up pyqtgraph windows showing the raw image, the
                    median image and their difference. Off by default -- these
                    used to be opened unconditionally on every call, which
                    meant three live GraphicsLayoutWidgets per acquisition.
                    Matches the `debug` kwarg on
                    ConsecutiveImageAnalyzer.removeCosmics.
        :return:
        """
        d = np.array(self.raw_array)

        med = ndimage.median_filter(d, size=(d.shape[0], 1), mode='wrap')
        meanMedian  = med.mean(axis=0)
        # Construct a cutoff for each pixel. It was kind of guess and
        # check
        cutoff = meanMedian * medianRatio + noiseCoeff * np.std(meanMedian[:100])

        log.debug("CRR shapes: d={}, med={}, meanMedian={}, cutoff={}".format(
            d.shape, med.shape, meanMedian.shape, cutoff.shape))

        winlist = []
        if debug:
            win = pg.GraphicsLayoutWidget()
            win.setWindowTitle("Raw Image")
            p1 = win.addPlot()

            img = pg.ImageItem()
            img.setImage(d.copy().T)
            p1.addItem(img)

            hist = pg.HistogramLUTItem()
            hist.setImageItem(img)
            win.addItem(hist)

            win.nextRow()
            p2 = win.addPlot(colspan=2)
            p2.plot(np.sum(d, axis=1))
            win.show()
            winlist.append(win)

            win2 = pg.GraphicsLayoutWidget()
            win2.setWindowTitle("Median Image")
            p1 = win2.addPlot()

            img = pg.ImageItem()
            img.setImage(med.T)
            p1.addItem(img)

            hist = pg.HistogramLUTItem()
            hist.setImageItem(img)
            win2.addItem(hist)

            win2.nextRow()
            p2 = win2.addPlot(colspan=2)

            p2.plot(np.sum(med, axis=1)/4)
            win2.show()
            winlist.append(win2)

            win2 = pg.GraphicsLayoutWidget()
            win2.setWindowTitle("d-m")
            p1 = win2.addPlot()

            img = pg.ImageItem()
            img.setImage((d - med).T)
            p1.addItem(img)

            hist = pg.HistogramLUTItem()
            hist.setImageItem(img)
            win2.addItem(hist)

            win2.nextRow()
            p2 = win2.addPlot(colspan=2)

            p2.plot((d - med)[0,:], pen='w')
            p2.plot((d - med)[1,:], pen='g')
            p2.plot((d - med)[2,:], pen='r')
            p2.plot((d - med)[3,:], pen='y')
            p2.plot(cutoff, pen='c')
            win2.show()
            winlist.append(win2)

        self.winlist = winlist
        # Find the bad pixel positions
        # Note the [:, None] - needed to cast the correct shapes
        badPixs = np.argwhere((d - med)>(cutoff))
        if badPixs.size:
            # Replace each cosmic by the mean of the rest of its row. Masking
            # them all out at once and using nanmean does this in one pass
            # instead of rebuilding an index list per bad pixel; it also keeps
            # other cosmics in the same row out of the average, which the old
            # sequential loop did not (see ConsecutiveImageAnalyzer.
            # removeCosmics, which already worked this way).
            rows, cols = badPixs[:,0], badPixs[:,1]
            masked = d.astype(float)
            masked[rows, cols] = np.nan
            rowMeans = np.nanmean(masked, axis=1)
            d[rows, cols] = rowMeans[rows]
        self.clean_array = np.array(d)


    def make_spectrum(self):
        '''
        Integrates over vertical axis of the cleaned image

        I'm not exactly sure y_min and y_max are counting from the same side as
        in the UI.
        '''
        if not self.isSeries:
            self.spectrum = self.clean_array[self.equipment_dict['y_min']:self.equipment_dict['y_max'],:].sum(axis=0)
            wavelengths = gen_wavelengths(self.equipment_dict['center_lambda'],
                                          self.equipment_dict['grating'],
                                          self.spectrum.shape[0])
            self.spectrum = np.vstack((wavelengths, self.spectrum)).T

        else:
            self.spectrum = self.raw_array.sum(axis=0)
            wavelengths = gen_wavelengths(self.equipment_dict['center_lambda'],
                                          self.equipment_dict['grating'],
                                          self.spectrum.shape[0])
            self.spectrum = np.vstack((wavelengths, self.spectrum)).T


    def isEmpty(self):
        """
        returns whether the raw_array is empty
        """
        return bool(self.raw_array.size)

    def updateSaveSettings(self, other):
        """
        Given an other EMCCD_image, this will populate this objects
        save settings (img no, filename, etc)
        """
        self.filename = other.file_name
        self.file_no = other.file_no
        self.description = other.description
        self.equipment_dict.update(other.equipment_dict)

    def addSpectrum(self, other):
        if isinstance(other, EMCCD_image):
            newSpec  = np.array(other.spectrum[:,1])
            pulse = other.equipment_dict["fel_pulses"]
            pulse = 1 if pulse == 0 else pulse
            newSpec /= pulse
            self.equipment_dict["fieldStrength"].append(other.equipment_dict["fieldStrength"])
            self.equipment_dict["fieldInt"].append(other.equipment_dict["fieldInt"])
            self.equipment_dict["fel_pulses"].append(other.equipment_dict["fel_pulses"])
            self.equipment_dict["fel_pulses"].append(other.equipment_dict["fel_pulses"])
            self.raw_array = np.row_stack((self.raw_array, newSpec))

        elif isinstance(other, np.ndarray):
            self.raw_array = np.row_stack((self.raw_array, other))

    def initializeSeries(self):
        """
        To be called when the class will hold a collection
        of the FVB spectra. Sets up self.spectra and
        makes equipment dict ready to append new values
        """
        self.isSeries = True
        self.clean_array = None
        pulse = self.equipment_dict["fel_pulses"]
        pulse = 1 if pulse == 0 else pulse
        self.raw_array = self.spectrum[:,1].reshape((1, -1))/pulse
        self.file_no += "seriesed"
        self.equipment_dict["fieldStrength"] = [self.equipment_dict["fieldStrength"]]
        self.equipment_dict["fieldInt"] = [self.equipment_dict["fieldInt"]]
        self.equipment_dict["fel_pulses"] = [self.equipment_dict["fel_pulses"]]

class PL_image(EMCCD_image):
    pass

class Abs_image(EMCCD_image):
    origin_import = '\nWavelength,Raw Trans\nnm,arb. u.'
    def __init__(self, raw_array=None, file_name='', file_no=None, description='', equipment_dict=None):
        super(Abs_image, self).__init__(raw_array, file_name, file_no, description, equipment_dict)
        self.abs_spec = None
    def __eq__(self, other):
        if type(other) is not type(self):
            print("not same type: {}/{}/{}".format(type(other), type(self), type(Abs_image())))
            return False
        if self.equipment_dict["gain"] != other.equipment_dict["gain"]:
            return False
        if self.equipment_dict["exposure"] != other.equipment_dict["exposure"]:
            return False
        if self.equipment_dict["grating"] != other.equipment_dict["grating"]:
            return False
        if self.equipment_dict["center_lambda"] != other.equipment_dict["center_lambda"]:
            return False
        return True

    def __truediv__(self, other):
        # self is the transmission spectrum
        # other is the other data

        if type(other) is not type(self):
            raise TypeError("Cannot divide {}".format(type(other)))
        ret = copy.deepcopy(self)
        abs_spec = -10 * np.log10(self.spectrum[:, 1] / other.spectrum[:, 1])
        wavelengths = gen_wavelengths(self.equipment_dict['center_lambda'],
                                      self.equipment_dict['grating'],
                                      self.spectrum.shape[0])

        # First is blank
        # other is transmission
        ret.spectrum = np.vstack((wavelengths, self.spectrum[:, 1],
                                  other.spectrum[:, 1], abs_spec)).T
        return ret



    def __div__(self, other):
        # self is the transmission spectrum
        # other is the other data
        if type(other) is not type(self):
            raise TypeError("Cannot divide {}".format(type(other)))
        ret = copy.deepcopy(self)
        abs_spec = -10*np.log10(self.spectrum[:,1] / other.spectrum[:,1])
        wavelengths = gen_wavelengths(self.equipment_dict['center_lambda'],
                                      self.equipment_dict['grating'],
                                      self.spectrum.shape[0])

        # First is blank
        # other is transmission
        ret.spectrum = np.vstack((wavelengths, self.spectrum[:,1],
                                  other.spectrum[:,1], abs_spec)).T
        return ret

    def setAsSequence(self):
        """
        This function is called by the expwidget when this object
        becomes a sequence image. Sets things up to be ready to take multiple
        images. Updates things such as FEL pulses/stats in the equipment dict
        to be lists to append to.

        Need to subclass here to force no norm factor. This prevents
        normalization to FEL pulses, which isn't good for abs (especially
        if reference doesn't have FEL on and is normalized differently)
        :return:
        """
        self.imageSequence.clearImages()
        self.imageSequence.addImage(self, normFactor=1)
        self.isSequence = True
        if "fieldStrength" in self.equipment_dict:
            self.equipment_dict["fieldStrength"] = [
                self.equipment_dict["fieldStrength"]
            ]

            self.equipment_dict["fieldInt"] = [
                self.equipment_dict["fieldInt"]
            ]

            self.equipment_dict["fel_pulses"] = [
                self.equipment_dict["fel_pulses"]
            ]

    def addNewImage(self, newImage):
        """
        This function should be called by an object
        which serves to act as a collection of multiple images.

        This will collect the FEL changes (pulses, strength, etc)
        :param newImage:
        :type newImage: EMCCD_image
        :return:
        """
        if "fieldStrength" in self.equipment_dict:
            self.equipment_dict["fieldStrength"].append(
                newImage.equipment_dict["fieldStrength"]
            )

            self.equipment_dict["fieldInt"].append(
                newImage.equipment_dict["fieldInt"]
            )

            self.equipment_dict["fel_pulses"].append(
                newImage.equipment_dict["fel_pulses"]
            )
        self.imageSequence.addImage(newImage, normFactor=1)


class Image_Reprocesser(object):
    """
    Sometimes, things fuck up and you need to reprocess data from the raw images. This
    class helps you do that. Currently assumes you want to do this for an HSG image.
    Mimic's the logic behind processImage from the ExpWidgs classes

    Typical usage would be to pass a list of image filenames and background file names
    in the init


    I think the biggest thing that'll need to be done is changing normalization factors
    Pretty sure that'll be done by changing
        self.prevDataEMCCD.imageSequence._normFactors
    Which is a list of normalization factors, general FEL pulses in each image.

    Example usage:

    from image_spec_for_gui import Image_Reprocesser as IR
    images = hsg.natural_glob("Images", "*")
    backs = hsg.natural_glob("Backgrounds", "*")
    repr = IR(images = images, backgrounds=backs)
    repr.prevDataEMCCD.imageSequence._normFactors = [32, 32, 32, 32]
    repr.processBackgroundSequence()
    repr.processImageSequence(saveSpectrum=".")
    """
    DataClass = HSG_image
    def __init__(self, images=None, backgrounds=None):
        self.curDataEMCCD = None
        self.prevDataEMCCD = None
        self.curBackEMCCD = None
        self.prevBackEMCCD = None

        if images is not None:
            self.addImages(list(images))
        if backgrounds is not None:
            self.addBackgrounds(list(backgrounds))

    def addBackground(self, fname):

        import hsganalysis as hsg
        d, h = hsg.get_data_and_header(fname)
        self.curBackEMCCD = self.DataClass(d,
               file_name=h["filename"],
               file_no=h["fileno"],
               equipment_dict=h)
        self.curBackEMCCD.make_spectrum()
        self.curBackEMCCD.clean_array = self.curBackEMCCD.raw_array
        self.addBackgroundSequence()

    def addBackgrounds(self, fnames):
        for fname in fnames: self.addBackground(fname)

    def addImage(self, fname):
        import hsganalysis as hsg
        d, h = hsg.get_data_and_header(fname)
        self.curDataEMCCD = self.DataClass(d,
               file_name=h["filename"],
               file_no=h["fileno"],
               equipment_dict=h)
        self.curDataEMCCD.make_spectrum()
        self.curDataEMCCD.clean_array = self.curDataEMCCD.raw_array
        self.addImageSequence()


    def addImages(self, fnames):
        for fname in fnames: self.addImage(fname)

    def addImageSequence(self):
        try:
            self.prevDataEMCCD.addNewImage(
                self.curDataEMCCD
            )
        except (AttributeError, ValueError) as e:
            self.prevDataEMCCD = None
        if self.prevDataEMCCD is None:
            self.prevDataEMCCD = copy.deepcopy(self.curDataEMCCD)
            self.prevDataEMCCD.setAsSequence()

    def addBackgroundSequence(self):
        try:
            self.prevBackEMCCD.addNewImage(
                self.curBackEMCCD
            )
        except (AttributeError, ValueError):
            self.prevBackEMCCD = None
        if self.prevBackEMCCD is None:
            self.prevBackEMCCD = copy.deepcopy(self.curBackEMCCD)
            self.prevBackEMCCD.setAsSequence()
            self.prevBackEMCCD.imageSequence.ignoreNormFactors = True

    def processBackgroundSequence(self, saveImages = False):
        d, std = self.prevBackEMCCD.imageSequence.removeCosmics()
        self.prevBackEMCCD.clean_array = d
        self.prevBackEMCCD.std_array = std

        if saveImages is not False and isinstance(isinstance(saveImages, str)):
            self.prevBackEMCCD.save_images(
                folder_str=saveImages,
                data=std,
                fmt='%f',
                postfix="_std"
            )
            self.prevBackEMCCD.save_images(
                folder_str=saveImages,
                data=d,
                postfix="_seq"
            )
        self.curBackEMCCD = self.prevBackEMCCD
        self.prevBackEMCCD = None

    def processImageSequence(self, saveSpectrum = False, saveImages = False):
        d, std = self.prevDataEMCCD.imageSequence.removeCosmics()

        d, sigpost, sigT = self.prevDataEMCCD.imageSequence.subtractImage(
            self.curBackEMCCD
        )

        self.prevDataEMCCD.clean_array = d
        self.prevDataEMCCD.std_array = sigpost

        if saveImages is not False and isinstance(isinstance(saveImages, str)):
            self.prevDataEMCCD.save_images(
                folder_str=saveImages,
                data=sigpost,
                fmt='%f',
                postfix="_stdpost"
            )
            self.prevDataEMCCD.save_images(
                folder_str=saveImages,
                data=sigT,
                fmt='%f',
                postfix="_stdT"
            )
            self.prevDataEMCCD.save_images(
                folder_str=saveImages,
                data=d,
                postfix="_seq",
                fmt='%f'
            )
        self.prevDataEMCCD.make_spectrum()
        oh = self.prevDataEMCCD.origin_import.splitlines()
        oh[1] += ",error"
        oh[2] += ",arb.u."
        oh.append(
            "Wavelength,{},error".format(self.prevDataEMCCD.equipment_dict["series"]))
        oh = "\n".join(oh)

        if saveSpectrum is not False and isinstance(saveSpectrum, str):
            self.prevDataEMCCD.save_spectrum(
                saveSpectrum,
                postfix="seq",
                origin_header=oh
            )

def gen_wavelengths(center_lambda, grating, npix=1600):
    '''
    Thin wrapper around the (cached) calculation. The result depends only on
    (center_lambda, grating, npix), all of which change rarely, but
    make_spectrum() calls this on every frame -- including once per frame in
    continuous mode -- so the ~20-term trig expression below is memoized.
    A copy is handed out so callers can't corrupt the cached array.
    '''
    output = _gen_wavelengths(center_lambda, grating, npix)
    return None if output is None else output.copy()


@functools.lru_cache(maxsize=32)
def _gen_wavelengths(center_lambda, grating, npix=1600):
    '''
    This returns an npix element list of wavelengths for each pixel in the EMCCD based on grating and center wavelength
    
    grating = which grating, 1 or 2
    center = center wavelength in nanometers
    npix = number of pixels along the wavelength axis. Defaults to the full
           1600-pixel chip; pass the real width when binning or using a
           sub-ROI, or the axis won't line up with the spectrum.
    '''
    b = 0.75 # length of spectrometer, in m
    k = -1.0 # order looking at
    r = 16.0e-6 # distance between pixles on CCD

    if grating == 1:
        d = 1./1800000.
        gamma = 0.213258508834
        delta = 1.46389935365
    elif grating == 2:
        d = 1./1200000.
        gamma = 0.207412628027
        delta = 1.44998344749
    elif grating == 3:
        d = 1./600000.
        gamma = 0.213428934011
        delta = 1.34584754696
    else:
        print("What a dick, that's not a valid grating")
        return None
    
    center = center_lambda*10**-9
    # Pixel offsets from the chip centre. Written out this way rather than as
    # arange(-799., 801.) so it generalises to other widths; for npix=1600 it
    # produces exactly the same -799..800 the hardcoded version did.
    wavelength_list = np.arange(npix, dtype=float) - (npix//2 - 1)
    
    output = d*k**(-1)*((-1)*np.cos(delta+gamma+(-1)*np.arccos((-1/4)*(1/np.cos((1/2)*gamma))**2*(2*(np.cos((1/2)*gamma)**4*(2+(-1)*d**(-2)*k**2*center**2+2*np.cos(gamma)))**(1/2)+d**(-1)*k*center*np.sin(gamma)))+np.arctan(b**(-1)*(r*wavelength_list+b*np.cos(delta+gamma))*(1/np.sin(delta+gamma))))+(1+(-1/16)*(1/np.cos((1/2)*gamma))**4*(2*(np.cos((1/2)*gamma)**4*(2+(-1)*d**(-2)*k**2*center**2+2*np.cos(gamma)))**(1/2)+d**(-1)*k*center*np.sin(gamma))**2)**(1/2))   
    
    output = (output + center)*10**9
    return output


def calc_THz_intensity(total_energy, window_trans=1, sample_eff_field=1, pulse_width=37,
                       ratio=None, radius=0.05, ito_reflect=0.7):
    """
    This will calculate the THz intensity at the sample during the cavity dump.
    Do not enter a ratio if you want to do an average intensity calculation.

    total_energy - the total energy in the FEL pulse, in mJ
    pulse_width - the FWHM of the pulse as measured by the fast pyro, in ns
                  if you want for cavity dump intensity, use FWHM of the front
                  porch. Assumed to be 37 ns (pulse width for cavity dump
                  based on photon travel time for two round trips in undulator)
    window_trans - the power transmission of the cryostat window
    sample_eff_field - the effective _field_ at the front of the sample
    ratio - the ratio of the cavity dump to the front porch
    radius - the radius of the FEL spot, assumed to be 0.05 cm
    ito_reflect - the power reflection of the ITO beam combiner, assumed to be
                  around 0.7

    return - the intensity in the FEL spot in W/cm^2
    """
    area = np.pi * (radius)**2
    if ratio is not None:
        # power = 1e-3 * total_energy / (37e-9 + (pulse_width * 1e-9) / ratio)
        power = 1e-3 * total_energy * ratio/ (pulse_width * 1e-9)
    else:
        power = 1e-3 * total_energy / (pulse_width * 1e-9)
    return ito_reflect * window_trans * sample_eff_field**2 * power / area

def calc_THz_field(intensity, n=3.59):
    """
    This will calculate the THz field strength in the sample

    intensity - the intensity of the THz field
    n - the index of the material at the THz frequency, assumed to be 3.59 for GaAs

    return - the peak electric field in V/cm
    """
    return (2 * intensity / (8.85e-12 * 2.99e8 * n))**0.5
