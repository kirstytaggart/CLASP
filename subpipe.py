#self.fail in report:
#0 - went ok
#1 - Alignment failed
#2 - seeing ratio failed
#3 - sum_kernel poor in both directions

import os
import sys
import logging
import atexit
import shutil
from glob import glob
from datetime import datetime

from pyraf import iraf
import numpy as np
import pyfits

import pipemodules.functs as functs
import pipemodules.cosmics as cosmics
import pipemodules.myalardwrap as alardwrap
import pipemodules.f2n as f2n

# stops pyfits throwing out annoying warnings about file size not expected:
import warnings
warnings.filterwarnings('ignore')

# load necessary iraf packages
iraf.nproto(_doprint=0)
iraf.noao(_doprint=0)
iraf.digiphot(_doprint=0)
iraf.apphot(_doprint=0)

# the file and directory path to this script, in case you call it from 
# another directory, so relative paths to the script are still intact
FILEPATH = os.path.realpath(__file__)
FILEDIR = os.path.dirname(FILEPATH)

# allows f2n_fonts to be found (used in making pngs)
sys.path.append(os.path.join(FILEDIR,'pipemodules'))

# define some variables for the pipeline into this module's name space
# WARNING Make sure there is nothing nasty in here to be executed
#try:
#    execfile(os.path.join(FILEDIR,'PIPEcfg.py'))
#except IOError:
#    raise IOError('ERROR\tcannot exec pipe config file (%s)'\
#                  % os.path.join(FILEDIR,'PIPEcfg.py'))

def execpipecfg(directory,pipecfg):
    # define some variables for the pipeline into this module's name space
    # use the PIPEcfg.py file in the workdir, moved there by photpipe
    # WARNING: Make sure there is nothing nasty in here to be executed!!!
    pipecfgfile = os.path.join(directory,pipecfg)
    try:
        execfile(pipecfgfile,globals())
    except IOError:
        raise IOError('Cannot find %s.' % pipecfgfile)

class FlushFile(object):
    """
    custom stdout behaviour
    
    this will flush stdout after every write - helps with output to gui
    """
    def __init__(self, f):
        self.f = f
    def write(self, x):
        self.f.write(x)
        self.f.flush()
    def flush(self):
        self.f.flush()
# Assign stdout to our custom class
sys.stdout = FlushFile(sys.stdout)

# set up the logger defined in run-subpipe
logger = logging.getLogger('run-subpipe.subpipe')

class SubtractionPipeline(object):
    
    def __init__(self,image,template,fringeframe=None,bpm=None,trim=0,
                 image_iter=2,reverseflag=0,ISIScfg='ISIScfg.py',
                 PIPEcfg='PIPEcfg.py',stamps='',cleantemplate=1,temp_iter=2):
        self.image = image
        self.template = template
        self.fringeframe = fringeframe
        self.bpm = bpm
        self.trim = trim
        self.image_iter = image_iter
        self.ISIScfg = ISIScfg
        self.PIPEcfg = PIPEcfg
        self.reverseflag = reverseflag
        self.stamps = stamps
        self.cleantemplate = cleantemplate
        self.temp_iter = temp_iter

        self.fail = None

        # get some info on the template and clean it as required, due to 
        # `singleton` this will only be done once per call
        self.t = singleton(GetImageInfo,self.template,
                           info='getting template information')
        if self.cleantemplate:
            # i.e. remove fringing and bpm as well as CR and trim
            #logger.info('full cleaning of template')
            singleton(CleanTemplate,self.template,self.temp_iter,self.trim,
                      self.fringeframe,self.bpm,
                      info='full cleaning of template')
        elif self.temp_iter != 0:
            # i.e. remove only CR and trim
            #logger.info('removing cosmic rays from template')
            singleton(CleanTemplate,self.template,self.temp_iter,self.trim,
                      info='removing cosmic rays from template')
        else:
            pass

        logger.info('getting image information')
        self.i = GetImageInfo(self.image)

        self.main()


    def get_report_info(self):
        """
        returns a dictionary of pertinent parameters and variables from the 
        instance to be put into a report file.
        """
        info = {'image':os.path.basename(self.image),
                'object':self.i.object,
                'ifwhm':self.i.fwhm,
                'istddev':self.i.stats['stddev'],
                'tfwhm':self.t.fwhm,
                'tstddev':self.t.stats['stddev'],
                'aligned':self.code,
                'failcode':self.fail}

        if self.fail:
            info['reverse'] = 'n/a'
            for x in ['submean','substddev','subtstddev','seeingratio',
                      'sum_kernel']:
                info[x] = 0           
        else:
            info['seeingratio'] = self.seeingratio
            info['reverse'] = 'YES' if self.reverse else 'NO'
            info['submean'] = self.s.stats['mean']
            info['substddev'] = self.s.stats['stddev']
            info['subtstddev'] = self.s.stats['tstddev']
            info['sum_kernel'] = self.sum_kernel
        return info


    def make_pngs(self):
        """
        Wrapper method to call make_png() function on aligned and subtracted
        images.
        """
        if not self.fail:
            logger.debug('creating png of aligned and subtracted FITS files')
            #make_png(self.alignedimage,
            #         z1=self.a.stats['mean']-2*self.a.stats['stddev'],
            #         z2=self.a.stats['mean']+5*self.a.stats['stddev'])
            make_png(self.alignedimage)
            make_png(self.subimage)
        else:
            logger.debug('skipping pngs as pipe failed for this image')


    def main(self):
        """
        The big dog.

        Runs the full works.
        """

        if self.fringeframe:
            logger.info('defringing image using %s' % self.fringeframe)
            defringe(self.image,self.fringeframe)
        if self.bpm:
            logger.info('removing bad pixel mask')
        if self.image_iter:
            logger.info('removing cosmic rays with %i iteration(s)'
                        % self.image_iter)
        if self.bpm or self.image_iter != 0:
            remove_cosmetics(image = self.image,
                             cositer = self.image_iter,
                             bpm = self.bpm,
                             gain = self.i.gain,
                             readnoise = self.i.readnoise,
                             satlevel = IMAGESATLIMIT,
                             trim = self.trim)
        
        if self.trim:
            logger.info('trimming %i pixels from image' % self.trim)
            trim_border(self.image,self.trim)

        # We may need to alter this depending on number of objects we find
        global XYXYMATCH

        # find objects in template if we haven't already
        tempcoo = os.path.splitext(self.template)[0]+'.coo'
        try:
            open(tempcoo)
        except IOError:
            logger.info('running SExtractor on template')
            tempcoo = os.path.splitext(self.template)[0]+'.coo'
            tempobj,tempthresh = objectfind(self.template,
                                  imagesat=TEMPSATLIMIT,
                                  thresh=TEMPTHRESH,
                                  minobj=TEMPMINOBJ,maxobj=TEMPMAXOBJ)
            logger.info('found %i objects in template at threshold %i'\
                    % (tempobj,tempthresh))
            if tempobj < XYMIN and XYXYMATCH:
                logger.warning('num objects found in template < XYMIN.')
                logger.warning('switching off XYXYMATCH aligning!')
                XYXYMATCH = False
                if WREGISTER is False:
                    logger.error('NO ALIGNMENT OPTIONS AVAILABLE!')
                    self.code = 'Nobj<XYMIN'
                    self.fail = 1
                    return
        else:
            tempthresh = TEMPTHRESH
                           # so that don't get AttributeErrors, only used when
                           # template starlist made with subtraction anyway

        #TODO save number of objects for photpipe's use later
        #FIXME self.numobj = tempobj

        # find objects in image
        logger.info('running SExtractor on image')
        imagecoo = os.path.splitext(self.image)[0]+'.coo'
        imageobj,imagethresh = objectfind(self.image,imagesat=IMAGESATLIMIT,
                               thresh=IMAGETHRESH,
                               minobj=IMAGEMINOBJ,maxobj=IMAGEMAXOBJ)
        logger.info('found %i objects in image at threshold %i'\
                    % (imageobj,imagethresh))
        if imageobj < XYMIN and XYXYMATCH:
                logger.warning('num objects found in image < XYMIN.')
                logger.warning('switching off XYXYMATCH aligning!')
                XYXYMATCH = False
                if WREGISTER is False:
                    logger.error('no alignment options available!')
                    self.code = 'Nobj<XYMIN'
                    self.fail = 1
                    return

        # align the image to the template using methods in PIPEcfg
        if WREGISTER or XYXYMATCH:  
            logger.info('aligning image to template')
            self.alignedimage,self.code = align_images(
                                             image = self.image,
                                             template = self.template,
                                             imagecoo = imagecoo,
                                             newimagethresh=imagethresh,
                                             tempcoo = tempcoo)
        else:
            logger.info('skipping alignment (WREGISTER and XYXYMATCH False)')
            self.alignedimage = self.image
            self.code = 'PREALIGNED'

        if not self.alignedimage:
            logger.error('ALIGNMENT FAILED! exiting the pipe')
            self.fail = 1
            return

        logger.info('subtracting template from image')
        self.subimage,self.reverse,self.seeingratio,self.sum_kernel = \
                              subtract_images(image = self.alignedimage,
                                              template = self.template,
                                              imagethresh = imagethresh,
                                              tempthresh = tempthresh,
                                              reverseflag= self.reverseflag,
                                              ISIScfg = self.ISIScfg,
                                              stamps = self.stamps)

        if np.isnan(self.seeingratio):
            logger.error('SEEINGRATIO FAILED! Exiting the pipe')
            self.fail = 2
            return
        if not self.subimage:
            logger.error('SUBTRACTION FAILED! Exiting the pipe')
            self.fail = 3
            return

        # copy header from aligned for subtracted image as ISIS neglects this
        logger.debug('updating subtracted header')
        subdata = pyfits.getdata(self.subimage)
        alignedhdr = pyfits.getheader(self.alignedimage)
        pyfits.update(self.subimage,subdata,alignedhdr)

        logger.info('getting aligned image information')
        self.a = GetImageInfo(self.alignedimage,rmzeros=True)
        logger.info('getting subtracted image information')
        self.s = GetImageInfo(self.subimage,subimage=True,rmzeros=True)
        
        # define the fwhm of the subtracted image as the fwhm of the frame
        # that didn't undergo convolution
        if self.reverse:
            self.s.fwhm = self.i.fwhm # template convolved
        else:
            self.s.fwhm = self.t.fwhm # image convolved


class GetImageInfo(object):
    """
    Class to store some information about the image and its header.

    INPUT
        image:
                the filepath of image to be examined
        subimage [False]:
                set to true if a subtracted image
        rmzeros [False]:
                remove from the data to be inspected all those pixels of value
                zero i.e. negate none overlapping regions for an aligned image
    """
    _instance = None

    def __init__(self,image,subimage=False,rmzeros=False,getfwhm=True):
        
        self.data,self.header = pyfits.getdata(image,header=True)
        self.stats = functs.get_stats(self.data,rmzeros=rmzeros)
        self.filter = functs.get_filt(self.header,FILTERKEYS)
        if not self.filter:
            logger.warning('couldn\'t determine filter for %s' 
                            % os.path.basename(image))
        else:
            logger.debug('found filter as `%s`' % self.filter)

        if not subimage:
            try:
                self.exptime = float(self.header[EXPHDR])
            except KeyError:
                logger.warning('couldn\'t find `%s` header' % EXPHDR)

            logger.debug('running SExtractor to estimate FWHM')
            starlist = alardwrap.runsex(image,thresh=10,sat=55000)
            if starlist == None: # i.e. Sextractor failed
                self.fwhm = np.nan
            else:
                self.fwhm = alardwrap.getmedianseeing(starlist)
            if type(self.fwhm) is not float or np.isnan(self.fwhm):
                logger.warning('SExtractor failed to determine FWHM')
                logger.warning('setting FWHM = %f in lieu of better info'
                               % FWHMDEFAULT)
                self.fwhm = FWHMDEFAULT

            self.date = functs.get_obsdate(self.header,DATEKEYS)
            if not self.date:
                logger.warning('float value for observation date not found'
                               '\n\tcheck DATEHDRS in PIPEcfg.py.')
                logger.info('setting date of observation to dummy value 1.0')
                self.date = 1.0
            else:
                logger.debug('found date as `%s`' % self.date)

            global WREGISTER
            try:
                wcs_err = self.header["WCS_ERR"]
                logger.debug('WCS_ERR header value = %s' % wcs_err)
            except KeyError:
                logger.debug('WCS_ERR key not found in header')
                wcs_err = 0
            if wcs_err != 0 and WREGISTER:
                logger.warning('switching off WREGISTER - WCS_ERR header value'
                               ' != 0.')
                WREGISTER = False

            self.object = self.header.get(OBJECTHDR,OBJECTNAME)
            self.gain = float(self.header.get(GAINHDR,GAIN))
            self.readnoise = float(self.header.get(RDNOISEHDR,RDNOISE))

        # Cut down on memory usage
        self.data = None
        self.header = None


class CleanTemplate(object):
    _instance = None
    def __init__(self,template,temp_iter,trim=0,fringeframe=None,bpm=None):
        if fringeframe:
            logger.info('defringing template using %s' % fringeframe)
            defringe(template,fringeframe)
        if bpm:
            logger.info('removing bad pixel mask from template')
        if temp_iter !=0:
            logger.info('removing template cosmic rays with %i iteration(s)'
                        % temp_iter)
        if trim:
            trim_border(template,trim)
        header = pyfits.getheader(template)
        gain = float(header.get(GAINHDR,GAIN))
        readnoise = float(header.get(RDNOISEHDR,RDNOISE))
        remove_cosmetics(image = template,
                         cositer = temp_iter,
                         bpm = bpm,
                         gain = gain,
                         readnoise = readnoise,
                         satlevel = TEMPSATLIMIT,
                         trim = trim)

############################## FUNCTIONS #####################################
def defringe(image,fringeframe,mask='CLASPobjmask.fits'):
    """
    Removes fringing from image.

    INPUT
        image: 
                the filepath of image for defringing
        fringeframe: 
                the fringeframe pattern filepath
    OUTPUT
        the defringed frame filepath

    Image is overwritten with the defringed version. iraf.rmfringe does the
    actual fringe removal after masking objects using iraf.objmasks
    """
    try:
        iraf.mscred(_doprint=0)
    except:
        logger.error('The iraf external package `mscred` is required to '
                     'remove fringing. Turn off fringe removal or '
                     'install `mscred`')
        sys.exit(5)
        
    if not outimage:
        outimage = image
    
    try:
        os.remove(mask)
    except OSError:
        pass

    iraf.unlearn(iraf.objmasks)
    iraf.objmasks(images = image,
                  objmasks = mask,
                  Stdout = 1)

    iraf.unlearn(iraf.rmfringe)
    iraf.rmfringe(input = image,
                  output = outimage,
                  fringe = fringeframe,
                  masks = mask+'[1]', #rmfringe requires the '[1]'
                  Stdout = 1) 
   
    os.remove(mask) 

    return outimage
      
  
def remove_cosmetics(image,cositer=1,bpm=None,savesat=False,trim=0,gain=2.0,
                    readnoise=5.0,satlevel=50000,verbose=False,outimage=None):
    """
    Cleans both cosmic rays and the bpm (if supplied).
    (Uses Malte Tewes python adaptation of L.A.Cosmic)

    INPUT
        image:
                filepath of image to be cleaned
        cositer [1]:
                number of CR detection iterations to perform
        bpm [None]:
                bad pixel mask relavent to `image`
        savesat [False]:
                save a saturated starmask of the image
        trim [0]:
                border around image to ignore for CR detection
        gain [2]:
                gain of the detector
        readnoise [5]:
                readnoise of detector
        satlevel [50000]:
                saturation level of `image`
        verbose [False]:
                run verbosely
        outimage [None]:
                filepath for cleaned frame to be written to
    OUTPUT
        the cleaned image filepath

    See cosmics.py for full documentation on the method. Pixels flagged in the
    bad pixel mask will be treated as CR and interpolated over. If outimage is
    None (or otherwise equates to False) then image is overwritten with the 
    cleaned version.
    """
    if not outimage:
        outimage = image

    # Run cosmics.py to clean, and then write the cleaned array to fits
    array,header = cosmics.fromfits(image)
    c = cosmics.cosmicsimage(array,gain=gain,readnoise=readnoise,
                             satlevel=satlevel,bpm=bpm,trimborder=trim,
                             verbose=verbose)
    c.run(maxiter=cositer)
    cosmics.tofits(outimage,c.cleanarray,header)
    
    if savesat:
        satmask = os.path.splitext(image)[0]+'.satmask.fits'
        cosmics.tofits(satmask,c.satstars,header)

    return outimage


def trim_border(image,trim,replacement_value=0):
    """
    Trims a border from image.

    INPUT
        image:
                the image to have its border fixed
        trim:
                size of border to fix in pixels
        replacement_value [0]:
                the value to replace pixel values with
    OUTPUT
        the trimmed image filepath

    Take a border of width `trim` around the image and sets all pixel values
    in this border to `replacement_value` (physical image size is unaffected!)
    The image is overwritten with the trimmed version.
    """

    hdu = pyfits.open(image,mode='update')

    hdu[0].data[:trim] = replacement_value
    hdu[0].data[-trim:] = replacement_value
    hdu[0].data[:,:trim] = replacement_value
    hdu[0].data[:,-trim:] = replacement_value
    hdu.flush()
    hdu.close(output_verify='ignore')
    return image


def align_images(image,template,imagecoo,tempcoo,
                 newimagethresh=None,outimage=None):
    """
    Aligns an image to template using wregister and xyxymatch.

    INPUT
        todo
    OUTPUT
        todo

    `newimagethresh` overrides the config file's IMAGETHRESH, as a better
    guess at a threshold that will satisfy object number limits
    """
    if outimage is None:
        outimage = image

    if newimagethresh is None:
        newimagethresh = IMAGETHRESH

    # a variable to hold info about the alignment to be put in the report
    aligninfo = ''

    # clean up after previous call
    for junk in ('/tmp/CLASPmatch.coo','/tmp/CLASPgeomap.db'):
        try:
            os.remove(junk)
        except OSError:
            pass

    if XYXYMATCH:
        # refind objects on wregistered image if required
        #if WREGISTER:
            #imagecoo = os.path.splitext(image)[0]+'.coo'
        #    logger.info('running SExtractor on wregistered image')
        #    imageobj,imagethresh = objectfind(image,imagesat=IMAGESATLIMIT,
        #                           thresh=newimagethresh,
        #                           minobj=IMAGEMINOBJ,maxobj=IMAGEMAXOBJ,
        #                           maxattempts=3)
        #    logger.info('found %i objects in image at threshold %i'\
        #            % (imageobj,imagethresh))
        #    if imageobj < XYMIN:
        #        logger.warning('num objects found in wreg image < XYMIN.')
        #        logger.warning('check WCS is correct in image and template!')
        #        #if WREGISTER:
        #        #    retval = None if wfail else outimage
        #        #else:
        #        #    retval = None
        #        return None,aligninfo+'BADWCS?'

        # use xyxymatch>geomap>geotran: 
        logger.info('trying to compute alignment with XYXYMATCH')
        xyxymatches = 0 # assign now since we conditionally assign later
                        # in the absence of IrafErrors
        iraf.unlearn(iraf.xyxymatch)
        try:
            xyout = iraf.xyxymatch(input = imagecoo,
                                   reference = tempcoo,
                                   output = '/tmp/CLASPmatch.coo',
                                   tolerance = XYTOL,
                                   nmatch = XYNMATCH,
                                   separation = XYSEP,
                                   verbose="yes",
                                   Stdout=1)
        except iraf.IrafError,e:
            logger.exception('XYXYMATCH failed due to IrafError!')
            #if not WREGISTER:
            #    logger.warning('XYXYMATCH failed!')
            #    return None,'XYERROR'
        else:
            logger.debug('XYXYMATCH output:\n'+'\n'.join(l for l in xyout if l))
            xyxymatches = int(xyout[-1].split()[0])
            logger.info('XYXYMATCH matched objects = %i' % xyxymatches)

        if xyxymatches < XYMIN and SEARCHRAD != 0:
            logger.warning('XYXYMATCH didn\'t find transformation initially')
            logger.info('attempting XYXYMATCH with objects located within '
                        'SEARCHRAD')
            ia = np.genfromtxt(imagecoo)
            ta = np.genfromtxt(tempcoo)
            linestoremove = []
            for x in range(len(np.atleast_2d(ia))):
                found = 0
                for y in range(len(np.atleast_2d(ta))):
                    r = ((ia[x,0] - ta[y,0])**2 + (ia[x,1] - ta[y,1])**2)**0.5
                    if r <= SEARCHRAD:
                        found = 1
                        break
                if not found:
                    linestoremove.append(x)
            linestoremove = list(set(linestoremove)) #remove duplicates
            linestoremove.sort(reverse=True) # prevent indexing errors      
            for line in linestoremove:
                ia = np.delete(ia,line,0)
            numcoincident = len(np.atleast_2d(ia))

            if numcoincident < XYMIN:
                logger.warning('objects within %i pixels on image'
                             ' and template (%i) < XYMIN' % (SEARCHRAD,
                                                              numcoincident))
                logger.info('check your XYMIN and SEARCHRAD values')
                #if not WREGISTER:
                #    return None,'NOCOIN*'
            else:
                for junk in (imagecoo,'/tmp/CLASPmatch.coo'):
                    try:
                        os.remove(junk)
                    except OSError:
                        pass
                        #save the reduced image object list
                        np.savetxt(imagecoo,ia,fmt='%13.3f')
                        #repeat xyxymatch with the reduced list
                        logger.info('repeating XYXYMATCH with reduced '
                                    'coordinate list')
                        try:
                            xyout = iraf.xyxymatch(input = imagecoo,
                                                reference = tempcoo,
                                                output = '/tmp/CLASPmatch.coo',
                                                tolerance = XYTOL,
                                                nmatch = XYNMATCH,
                                                separation = XYSEP,
                                                verbose = "yes",
                                                Stdout=1)
                        except iraf.IrafError,e:
                            logger.exception('XYXYMATCH failed due to '
                                             'IrafError!')
                            #if not WREGISTER:
                            #    logger.warning('XYXYMATCH failed!')
                            #    return None,'XYERROR'
                        else:
                            logger.debug('XYXYMATCH output:\n'+'\n'\
                                         .join(l for l in xyout if l))
                            xyxymatches = int(xyout[-1].split()[0])
                            logger.info('XYXYMATCH matched objects = %i' 
                                        % xyxymatches)       

        if xyxymatches < XYMIN:
            if SEARCHRAD > 0:
                logger.warning('XYXYMATCH didn\'t find transformation on '
                               'second pass')
            else:
                logger.warning('XYXYMATCH didn\'t find transformation '
                               'initially')
            logger.info('attempting XYXYMATCH using tolerance matching')
            # finally, let's try xyxymatch with the `tolerance` algorithm 
            # (triangles is used previous). see iraf docs for info.
    
            try:
                os.remove('/tmp/CLASPmatch.coo')
            except OSError:
                pass
            try:
                xyout = iraf.xyxymatch(input = imagecoo,
                                       reference = tempcoo,
                                       output = '/tmp/CLASPmatch.coo',
                                       matching='tolerance',
                                       tolerance = 5,
                                       nmatch = XYNMATCH,
                                       separation = XYSEP,
                                       verbose = "yes",
                                       Stdout=1)
            except iraf.IrafError,e:
                logger.exception('XYXYMATCH failed due to IrafError!')
                #if not WREGISTER:
                #    logger.warning('XYXYMATCH failed!')
                #    return None,'XYERROR'
            else:
                logger.debug('XYXYMATCH output:\n'+'\n'\
                             .join(l for l in xyout if l))
                xyxymatches = int(xyout[-1].split()[0])
                logger.info('XYXYMATCH matched objects = %i' % xyxymatches)

        if xyxymatches >= XYMIN:
            # xyxymatch has worked
            # now compute and perform the transformation
            ysize,xsize = pyfits.getdata(template).shape
            try:
                logger.debug('running GEOMAP to calculate transformation')
                iraf.unlearn(iraf.geomap)
                mapout = iraf.geomap(input = '/tmp/CLASPmatch.coo',
                                     database = '/tmp/CLASPgeomap.db',
                                     xmin = 1,
                                     xmax = xsize,
                                     ymin = 1,
                                     ymax=ysize,
                                     interactive='no',
                                     Stdout = 1)
                logger.debug('running GEOTRAN to perform transformation')
                iraf.unlearn(iraf.geotran)
                tranout = iraf.geotran(input = image,
                                       output = outimage,
                                       database = '/tmp/CLASPgeomap.db',
                                       transforms = '/tmp/CLASPmatch.coo',
                                       boundary = 'constant',
                                       constant = 0,
                                       Stdout = 1)
            except iraf.IrafError,e:
                logger.exception('GEOMAP/GEOTRAN failed due to IrafError!')
                #if not WREGISTER:
                #    logger.warning('XYXYMATCH failed!')
                #    return None,'GEOERROR'
            else:
                logger.debug('GEOMAP output:\n'+'\n'\
                             .join(l for l in mapout if l))
                logger.debug('GEOTRAN output:\n'+'\n'\
                             .join(l for l in tranout if l))
                logger.info('alignment sucessful with XYXYMATCH/GEOMAP/GEOTRAN')
                return outimage,'XYSUCCESS'
            

        logger.warning('XYXYMATCH failed to find a transformation solution')
        if not WREGISTER:
            return None,'XYFAIL'
        else:
            aligninfo+='XYFAIL '

    if WREGISTER:
        logger.info('attempting alignment with WREGISTER')
        iraf.unlearn(iraf.wregister)
        try:
            wregout = iraf.wregister(input = image,
                                     reference = template,
                                     output = outimage,
                                     boundary = 'constant',
                                     constant = 0,
                                     Stdout = 1)
        except iraf.IrafError,e:
            logger.exception('WREGISTER failed due to IrafError!')
            aligninfo += 'WREGFAIL'
            wfail = True
        else:
            logger.info('WREGISTER complete')
            aligninfo += 'WREGSUCCESS'
            wfail = False
        finally:    
            logger.debug('WREGISTER output:\n'+\
                        '\n'.join(l for l in wregout if l))
        retval = None if wfail else outimage
        return retval,aligninfo


def objectfind(image,imagesat=55000,thresh=10,minobj=10,maxobj=50,
                maxattempts=20):
    """
    Performs SExtractor recursively to find number of objects between
    given limits
    """

    logger.debug('SExtractor called with minobj=%i, maxobj=%i for '
                 '%i attempts' % (minobj,maxobj,maxattempts))

    # define a counter to ensure we don't end up in infinite loop
    counter = 0
    while True:
        counter += 1
        if counter > maxattempts:
            print ' '*50+'\r'
            logger.warning('reached max iterations! proceeding with numobj=%i'
                           % numobj)
            break
        
        starfile = alardwrap.runsex(image,thresh,imagesat)
        try:
            starfilearray = np.genfromtxt(starfile)
        except (IOError,TypeError):
            numobj = 0
        else:
            if len(starfilearray) == 0:
                numobj = 0
            else:
                numobj = len(np.atleast_2d(starfilearray))

        print 'attempt %i/%i\tthreshold: %i\t numobj: %i          \r'\
              % (counter,maxattempts,thresh,numobj),

        if numobj > maxobj: 
            thresh += 5
        elif numobj < minobj:
            thresh -= 2
        else:
            # clear current line of attempt/threshold info
            print ' '*50+'\r'
            break
        if thresh < 8:
            print ' '*50+'\r'
            logger.warning('low number of objects found by SExtractor'
                           ' at minimum threshold!')
            break


    # we don't want to be printing out hundreds of lines to the log file:
    with open(starfile) as f:
        out = f.readlines(30)        
    logger.debug('SExtractor output:\n'+''\
                 .join(l for l in out if not l.startswith('#')))

    try:
        os.remove(os.path.splitext(image)[0]+'.coo')
    except OSError:
        pass
    finally:
        shutil.copy(starfile,os.path.splitext(image)[0]+'.coo')
    return numobj,thresh



def subtract_images(image,template,ISIScfg='ISIScfg.py',imagethresh=25,
                    tempthresh=25,reverseflag=0,stamps=''):
    """
    Performs subtraction using Alard's ISIS code. 

    INPUT
        image:
                filepath of image to be subtracted
        template:
                filepath of template to subtract from image
        ISIScfg ['ISIScfg.py']:
                filepath of ISIS config file containing definitions of all 
                ISIS parameters
        reverseflag [0]:
                reverse modes for ISIS (see run-subpipe help) of stamps to use
        stamps ['']:
                file containing x and y coordinate
    OUTPUT
        subtracted image filepath
        rev:
                whether the suctraction was run in reverse or not
        ratio:
                the image to template seeing ratio

    Executes the file `ISIScfg` to define parameters for subtraction then
    calls on pipemodules.myalardwrap to deal with the subtraction. Returns
    a value determining the direction of convolution in ISIS, important for
    aperture correction determinations during photometry.
    Uses the value of sum_kernel (i.e. the relative flux contained in the
    convolved kernel to the non-convolved) as a measure of goodness of 
    subtraction, limits can e set in the PIPEcfg file. If deviates too much 
    then subtraction is ran in reverse and the old subtractions are appended
    with the extension '.one'.
    """
    execfile(ISIScfg,globals())
    baseimage = os.path.splitext(image)[0]
    try:
        rev,ratio,sum_kernel,alardcode = alardwrap.runalard(template,image,
                            imagethresh=imagethresh,tempthresh=tempthresh,
                            tempsat=st,
                            imagesat=si,nsx=nsx,nsy=nsy,sx=sx,
                            sy=sy,minval=minval,minstamp=minstamp,
                            kernelorder=kernelorder,reverseflag=reverseflag,
                            hms=hms,hss=hss,sg1=sg1,sg2=sg2,sg3=sg3,
                            deg_bg=deg_bg,removeconv=removeconv,
                            iterkernelsig=iterkernelsig,adapt=adapt,
                            stamps=stamps)
    except NameError:
        logger.exception('check ISIScfg file (%s). Parameter missing (see '
                         'traceback)' % ISIScfg)
        sys.exit(4)
    if alardcode:
            logger.info('runalard returned code %s for ISIS' % alardcode)
    if np.isnan(ratio) or np.isnan(sum_kernel):
        return None,rev,ratio,sum_kernel
    if reverseflag > 1:
        logger.info('reverseflag specified as %i, no sum_kernel checking done'
                    % reverseflag)
        subname = baseimage+'.sub.fits'
        return subname,rev,ratio,sum_kernel
    #TODO needs a rewrite so flows logically without repetition
    # use sum_kernel to determine if the subtracion went ok

    if (sum_kernel > MAXSUMKERNEL or sum_kernel < MINSUMKERNEL) and\
            sum_kernel != -1:
        logger.warning('sum_kernel = %6.4f Subtraction is probably poor!'
                       % sum_kernel)
        logger.info('running subtraction in reverse')
        logger.debug('renaming old subtraction files to *.one')
        for ext in ['.sum_kernel','.alardout','.sub.fits']:
            os.rename(baseimage+ext,baseimage+ext+'.one')
        logger.debug('flipping reverseflag switch')
        reverseflag = 0 if reverseflag else 1
        logger.debug('calling ISIS in reverse')
        rev,ratio,sum_kernel,alardfail = alardwrap.runalard(template,image,
                            imagethresh=imagethresh,tempthresh=tempthresh,
                            tempsat=st,
                            imagesat=si,nsx=nsx,nsy=nsy,sx=sx,
                            sy=sy,minval=minval,minstamp=minstamp,
                            kernelorder=kernelorder,reverseflag=reverseflag,
                            hms=hms,hss=hss,sg1=sg1,sg2=sg2,sg3=sg3,
                            removeconv=removeconv,
                            iterkernelsig=iterkernelsig,adapt=adapt,
                            stamps=stamps)
        # if it's still rubbish then probably misalignment or rubbish data
        if alardfail:
            logger.info('runalard returned code %s for ISIS' % alardfail)
        if np.isnan(sum_kernel):
            return None,rev,ratio,sum_kernel
        if (sum_kernel > MAXSUMKERNEL or sum_kernel < MINSUMKERNEL) and\
            sum_kernel != -1:
            logger.warning('sum_kernel = %6.4f Subtraction is probably poor!'
                       % sum_kernel)
            logger.warning('subtraction was deemed poor in both directions!')
            logger.info('check your data and (MIN/MAX)SUMKERNEL in ISIScfg')
            logger.debug('renaming reverse subtraction files to *.two')
            for ext in ['.sum_kernel','.alardout','.sub.fits']:
                os.rename(baseimage+ext,baseimage+ext+'.two')
            return None,rev,ratio,sum_kernel

    subname = baseimage+'.sub.fits'
    try:
        open(subname)
    except IOError:
        logger.warning('no file found at %s' % subname)
        return None,rev,ratio,sum_kernel

    return subname,rev,ratio,sum_kernel


def singleton(klass,*args,**kwargs):
    """
    Ensures only one instance of the class, klass, is made.

    INPUT
        klass:
                the class to be called
        args*:
                args to be passed to klass
    OUTPUT
        existing instantiated object if exists, otherwise the class is ran
    """
    if not klass._instance:
        logger.info(kwargs['info'])
        klass._instance = klass(*args)

    return klass._instance


def make_png(image):
    """
    Creates a png version of image with adjustable scaling.

    INPUT
        image:
                the filepath of the image to be made into a png
        z1 ['auto']:
                low level pixel value
        z2 ['auto']:
                upper level pixel value

    Takes a fits file and creates a 2x2 rebinned PNG image with scaling on
    pixel values z1 and z2 (see f2n.py documentation for further details).
    PNG files are named identical to fits counterparts with .png extension.
    """
    pngfilename = os.path.splitext(image)[0]+'.png'
    f2nimage = f2n.fromfits(image)    
    f2nimage.setzscale()
    f2nimage.rebin(2)
    f2nimage.makepilimage(scale='lin', negative=False)
    #f2nimage.writetitle(os.path.basename(image))
    f2nimage.tonet(pngfilename)


@atexit.register
def cleanup():
    junk = ['CLASPobjmask.fits','conv.fits','conv0.fits','default_config',
            'kernel_table','toto.bmp','imxymatch.1','/tmp/CLASPmatch.coo',
            '/tmp/CLASPgeomap.db','wregister.db','kernel_coeff0','STAMPS']
    for f in junk:
        try:
            os.remove(f)
        except OSError:
            pass

