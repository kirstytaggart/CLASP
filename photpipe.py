"""
self.fail:
0 - went ok
1 - couldn't get object magnitude from subtracted image
2 - cog model for aperture correction failed
"""
import os
import sys
import logging
import random
import time
import math
import subprocess
from glob import glob

from pyraf import iraf
import numpy as np

# load necessary iraf packages
iraf.tv(_doprint=0)
iraf.noao(_doprint=0)
iraf.digiphot(_doprint=0)
iraf.ptools(_doprint=0)
iraf.photcal(_doprint=0)
iraf.apphot(_doprint=0)

iraf.unlearn(iraf.display)
DS9DELAY = 15 # delay time in seconds to allow ds9 to load, extend if 
             # faling with error when trying to load images

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

logger = logging.getLogger('run-photpipe.photpipe')

def execpipecfg(workdir,pipecfg):
    # define some variables for the pipeline into this module's name space
    # use the PIPEcfg.py file in the workdir, moved there by photpipe
    # WARNING: Make sure there is nothing nasty in here to be executed!!!
    pipecfgfile = os.path.join(workdir,pipecfg)
    try:
        execfile(pipecfgfile,globals())
    except IOError:
        raise IOError('Cannot find %s.' % pipecfgfile)

class PhotometryPipeline(object):

    def __init__(self,subinstance,objcoords,smallap=3,largeap=15,
                 autopick=False):

        si = subinstance
        self.largeap = largeap
        self.smallap = smallap
        self.naperts = largeap-smallap+1 #num apertures mkapfile will extract
        self.apcorapertures = '%i:%i:1' % (self.smallap,self.largeap)
        self.objcoords = objcoords
        self.xcoo = self.objcoords.split(',')[0]
        self.ycoo = self.objcoords.split(',')[1]
        self.autopick = autopick

        self.subimage = si.subimage
        self.alignedimage = si.alignedimage
        self.template = si.template
        self.basetemplate = os.path.splitext(self.template)[0]
        self.basesubimage = os.path.splitext(self.subimage)[0]
        self.basealignedimage = os.path.splitext(self.alignedimage)[0]

        self.i = si.i # original image stats
        self.a = si.a # aligned image stats
        self.s = si.s # subtracted image stats
        self.t = si.t # template stats
        #self.numobj = si.numobj # number of objects found in template

        self.reverse = si.reverse
        self.obsdate = float(si.i.date)

        # store object coordinates in a file to be read by iraf.phot
        self.objcoordsfile = self.basetemplate+'.objcoo'
        with open(os.path.abspath(self.objcoordsfile),'w') as obj:
            obj.write('%s  %s' % (self.xcoo,self.ycoo))

        # make a list of stars to use for aperture correction/offset if needed
        self.starcoordsfile = self.basetemplate+'.starcoo'
        try:
            open(self.starcoordsfile)
        except IOError:
            logger.info('making starlist')
            if self.autopick:
                picked = self.auto_make_starlist()
                if not picked:
                    logger.warning('automated star selection failed, '
                                   'moving to manual')
                    madestars = self.make_starlist()
            else:
                madestars = self.make_starlist()
            if not madestars:
                logger.error('couldn\'t make starlist (or it\'s empty)')
                sys.exit(3)
        else:
            logger.info('starlist found as: %s' % self.starcoordsfile)     

        self.fail = None
        
        # start the main method
        self.main()

    def auto_make_starlist(self):
        """
        Attempt to select good aperture correction/offset stars automatically
        """
        #TODO
        #templatesex = np.genfromtxt(self.template+".stars")

        #fwhm = self.a.fwhm if self.a.fwhm >= self.t.fwhm else self.t.fwhm
        # use aperture sizes instead

        # ALIGNED IMAGE WON'T OVERLAP ENTIRELY!!! HOW TO SEXTRACT IN THIS 
        # REGION ONLY?!
        # Sextractor been last run on aligned image, shud be ok but don't know
        # if near edge of good image. use numpy of data, if near a zero region
        # then don't count
        #Sextractor coordinated are 1 indexed!!!!!
        #xycentres = templatesex[:,:2]
        # for xycentre in xycentre:
        #    check the requirements and remove if necessary
        # NEED TO ENSURE IS A STAR!
        # Sort by brightest stars and pick top numstars 
        #   (add as PIPEcfg.py option)

        # NEED TO REMOVE:
        # objects within a few fwhm of object coords
        # objects within a few fwhm + trim of edge
        # objects within a few fwhm of each other
        # objects that are too bright/dim

        return False #FIXME

    def make_starlist(self):
        """
        Create a file with x and y pixel locations of the stars to be used
        for aperture correction and offset.
        OUTPUT: file 'starcoords' in working directory
        TODO
        """
        # let's load ds9...
        ds9 = subprocess.Popen(['ds9'])

        # SExtractor numobj - will fail if tempcoo has no object but that
        # shouldn't be the case.
        a = np.genfromtxt(self.basetemplate+'.coo')
        numobj = len(np.atleast_2d(a))
        # now load the template and mark the stars in the ds9 window
        loaded = False
        for i in range(DS9DELAY):
            try:
                iraf.display(self.template,1)
            except iraf.IrafError:
                time.sleep(1)
            else:
                loaded = True
                break
        if not loaded:
            logger.error('couldn\'t display image into ds9')
            return False

        iraf.tvmark(frame=1,
                    coords=self.basetemplate+'.coo',
                    mark='circle',
                    col=204,
                    radii=3,
                    number='yes',
                    nxoffset=2,
                    nyoffset=2)

        # let the user select the stars they wish to use and record them
        print 'INFO\tenter the numbers of the stars to use for aperture'
        print '    \tcorrection, one at a time.'
        print 'INFO\twhen you\'re done, type "done".'
        print 'INFO\ttype "startover" to clear selections and begin again.'
        print 'INFO\t(input is ignored if input > numobj or a repeat)'
        starstouse = []
        while True:
            starnum = raw_input()
            if starnum == 'done': break
            if starnum == 'startover':
                print 'INFO\tcleared list, start again:'
                starstouse = []
                continue
            try:
                starnum = int(starnum)
                                                     #FIXME self.numobj
                if starnum not in starstouse and starnum <= numobj and\
                   starnum > 0:
                    starstouse.append(starnum)
                    print 'star {0} added'.format(starnum)
            except ValueError:
                print 'WARNING\tdidn\'t understand that input'

        # kill ds9 if the user hasn't already
        if ds9.poll() == None:
            ds9.kill()

        logger.info('stars chosen for aperture correction/offset:')
        logger.info(starstouse)
        centres = a[:,:2]
        # reduce the centres list to those desired by user...
        centrestouse = centres[[i-1 for i in starstouse],:]
        np.savetxt(self.starcoordsfile,centrestouse,fmt="%8.3f")

        return starstouse

    def calculate_aperture_correction(self,template=False):
        """
        do aperture correction photometry on starlist then use mkapfile to
        calculate the correction, usable by both template or image
        """
        if template:
            image = self.template
            photoutput = self.templatestarphotfile
            apcorfile = self.templateapcorfile
            mkapfile = self.templatemkapfile
            stats = self.t
        else:
            image = self.alignedimage
            photoutput = self.imagestarphotfile
            apcorfile = self.imageapcorfile
            mkapfile = self.imagemkapfile
            stats = self.a

        # do the aperture correction photometry
        logger.debug("performing aperture correction photometry")
        run_phot(image = image,
                 coords = self.starcoordsfile,
                 apertures = self.apcorapertures,
                 output = photoutput,
                 fwhm = stats.fwhm,
                 sigma = stats.stats["stddev"],
                 datamin = stats.stats["datamin"],
                 datamax = IMAGESATLIMIT,
                 ccdread = RDNOISEHDR,
                 readnoise = self.a.readnoise,
                 gain = GAINHDR,
                 epadu = self.a.gain,
                 exposure = EXPHDR,
                 itime = self.a.exptime)
        # run iraf.mkapfile to calcuate the aperture correction
        # attempt with 3&4 parameter cog models to maximise chance of sucess
        # NB: the 5 parameter cog model requires an airmass definition, since
        # not sure if that info is in headers, it's not attempted
        logger.debug("calculating aperture correction curve of growth")
        for n in (3,4):
            retmkap = run_mkapfile(photfiles = photoutput,
                                   naperts = self.naperts,
                                   apercors = apcorfile,
                                   magfile = mkapfile,
                                   nparams = n)
            time.sleep(0.5)
            if retmkap:
                logger.warning("iraf.mkapfile error")
            try:
                filesize = os.stat(mkapfile).st_size
            except OSError:
                pass
            else:
                if filesize != 0:
                    break
            if n == 4:
                logger.error("cog model failed. sorry about that")
                self.fail = 2
        return


    def get_lightcurve_info(self):
        if self.fail:
            return (os.path.basename(self.alignedimage),self.fail)

        info = {"image":os.path.basename(self.alignedimage),
                "obsdate":self.obsdate,
                "objmag":self.objmag_off,
                "objmagerr":self.objmagerr_off}
        return info


    def get_report_info(self):
        if self.fail:
            return (os.path.basename(self.alignedimage),self.fail)

        info = {"image":os.path.basename(self.alignedimage),
                "objmag_sm":self.objmag_sm,
                "objmagerr_sm":self.objmagerr_sm,
                "apcor":self.apcor,
                "apcorerr":self.apcorerr,
                "objmag_lrg":self.objmag_lrg,
                "objmagerr_lrg":self.objmagerr_lrg,
                "numoffsetstars":self.numoffsetstars,
                "offset":self.medianoffset,
                "offseterr":self.medianoffseterr,
                "objmag_off":self.objmag_off,
                "objmagerr_off":self.objmagerr_off}
        return info


    def main(self):
        """
        from subpipe instance to lightcurve file
        """
        self.objphotfile = self.basesubimage+".objphot"

        logger.info("running small aperture photometry on object")
        run_phot(image = self.subimage,
                 coords = self.objcoordsfile,
                 apertures = self.smallap,
                 output = self.objphotfile,
                 fwhm = self.s.fwhm, # = fwhm of non-convolved image
                 sigma = self.s.stats["stddev"],
                 datamin = self.s.stats["datamin"],
                 datamax = IMAGESATLIMIT,
                 ccdread = RDNOISEHDR,
                 readnoise = self.a.readnoise,
                 gain = GAINHDR,
                 epadu = self.a.gain,
                 exposure = EXPHDR,
                 itime = self.a.exptime)
        # dump relevant results and read magnitude
        dump = iraf.txdump(self.objphotfile,"MAG,MERR,PIER,PERROR",
                           "yes",headers="no",Stdout=1)
        objmag,objmagerr,pier,perr = dump[0].split()
        if objmag == "INDEF" or objmagerr == "INDEF":
            logger.error("iraf.phot failed to find perform photometry on "
                         "the object in subtracted frame."
                         "See %s for iraf.phot output" % self.objphotfile)
            self.fail = 1
            return

        self.objmag_sm = float(objmag)
        self.objmagerr_sm = float(objmagerr)
        logger.info("object magnitude with %i pixel aperture: %6.3f +/- %4.3f"
                    % (self.smallap,self.objmag_sm,self.objmagerr_sm))

        # perform aperture correction photometry and calculate it:
        # firstly for the template (if we haven't already)
        self.templatestarphotfile = self.basetemplate+".apcorphot"
        self.templatemkapfile = self.basetemplate+".mkap"
        self.templateapcorfile = self.basetemplate+".apcor"
        try:
            open(self.templatestarphotfile)
            open(self.templatemkapfile)
        except IOError:
            logger.info("calculating template aperture correction")
            self.calculate_aperture_correction(template=True)
            if self.fail:
                logger.error("cog model failed on template!"
                             "try selcting different stars to use")
                return
        # then for the image
        self.imagestarphotfile = self.basealignedimage+".apcorphot"
        self.imagemkapfile = self.basealignedimage+".mkap"
        self.imageapcorfile = self.basealignedimage+".apcor"
        logger.debug("calculating image aperture correction")
        self.calculate_aperture_correction(template=False)
        if self.fail:
            logger.error("cog model failed on image!"
                         "try selcting different stars to use")
            return

        # use the appropriate aperture correction to the object magnitude
        if self.reverse:
            apcortouse = self.imageapcorfile
        else:
            apcortouse = self.templateapcorfile
        with open(apcortouse) as f:
            i,self.apcor,self.apcorerr = f.readlines()[-1].split()
        self.apcor = float(self.apcor)
        self.apcorerr = float(self.apcorerr)
        logger.info("calculated aperture correction: %6.3f err: %6.3f" 
                    % (self.apcor,self.apcorerr))

        # apply it to the object magnitude
        self.objmag_lrg = self.objmag_sm + self.apcor
        self.objmagerr_lrg = \
                          (self.objmagerr_sm**2+self.apcorerr**2)**0.5
        logger.info("object magnitude for %i pixel aperture: %6.3f +/- %4.3f"
                    % (self.largeap,self.objmag_lrg,self.objmagerr_lrg))

        # find the image-template offset
        logger.info("calculating image-template median offset")
        ta = np.atleast_2d(np.genfromtxt(self.templatemkapfile))
        ia = np.atleast_2d(np.genfromtxt(self.imagemkapfile))
        offsets = []
        offsetserr = []
        for x in range(len(ia)):
            for y in range(len(ta)):
                r = ((ia[x,5] - ta[y,5])**2 + (ia[x,6] - ta[y,6])**2)**0.5
                if r < 3:
                    offsets.append(ta[y,7]-ia[x,7])
                    offsetserr.append((ta[y,8]**2+ia[x,8]**2)**0.5)
                    break
        self.numoffsetstars = len(offsets)         
        
        if self.numoffsetstars == 0:
            logger.warning("no offset stars found! skipping image template"
                           " offset calculation")
            offsets = [0]

        elif self.numoffsetstars < 3:
            logger.warning("low number ({}) of offset stars found!".format(
                           self.numoffsetstars))

        #self.avoffset = np.average(offsets) 
        # meanerr**2 = 1/SIGMA(1/err**2)
        #self.meanoffseterr = (1/sum(1/np.array(offsetserr)**2))**0.5

        # switched to median!
        self.medianoffset = np.median(offsets)
        # switched from mean to median, take error as just stddev of offsets? 
        self.medianoffseterr = np.std(offsets)

        logger.info("calculated median offset: %6.3f  err: %6.3f" 
                    % (self.medianoffset,self.medianoffseterr))
        logger.debug("applying image-template offset")
        self.objmag_off = self.objmag_lrg + self.medianoffset
        self.objmagerr_off = \
                    (self.objmagerr_lrg**2+self.medianoffseterr**2)**0.5
        logger.info("object magnitude (in template system): %6.3f +/- %4.3f"
                    % (self.objmag_off,self.objmagerr_off))


############################## FUNCTIONS #####################################

def get_object_coords(workdir):
    """
    allow user to select the object for photometry, and grab its coordinates

    INPUT
        workdir:
                a work directory from subpipe where there are one or more 
                *.sub.fits files to display
    OUTPUT
        xcoo,ycoo:
                the x and y pixel coordinates of the object the user selects
                in the string: "x,y"

    A random subtracted image is displayed ot the user. By pressing ',' with
    the cursor over the selected object, the x and y coordinates are extracted
    by imexam and presented to the user. If the image is poor or the object
    not obvious, or the output is garbage, then they can reject the
    coordinates and another image is displayed.
    """
    subimages = sorted(glob(os.path.join(workdir,"*.sub.fits")))
    if len(subimages) == 0:
        logger.error("no `*.sub.fits` images found in workdir")
        return False

    ds9 = subprocess.Popen(['ds9'])
    time.sleep(DS9DELAY/5.0)

    # display the first image
    imgnum = 0
    image = subimages[imgnum]
    # wait for ds9 to load by sleeping between attempts to open image
    loaded = False
    for i in range(int(math.ceil(DS9DELAY*0.8))):
        try:
            iraf.display(image,frame=1,Stderr=1)
        except iraf.IrafError:
            time.sleep(1)
        else:
            loaded = True
            break
    if not loaded:
        logger.error('couldn\'t display image into ds9')
        return False

    print '\nsetting object pixel coordinates:'
    print '\thover cursor over the object and press "," then "q".'
    print '\t - if image is poor press "q" first to open another.'
    # attempt to read x,y coordinates from user's input from imexam
    while True:
        imgnum += 1
        if imgnum == len(subimages):
            imgnum = 0
        imexamout = iraf.imexam(image,1,wcs='logical',keeplog='no',Stdout=1)
        if len(imexamout) > 1:
            try:
                xcoo = float(imexamout[-1].split()[0])
                ycoo = float(imexamout[-1].split()[1])
            except (IndexError,ValueError):
                print 'WARNING\tcouldn\'t read x and y coordinates, try again'
                continue
            finally:
                loadnew = False
        else:
            while True:
                answer = raw_input('QUERY\tattempt on next image? (y/n)\n')
                if answer == 'y':
                    loadnew = True   
                    print 'INFO\tloading next image...'   
                    image = subimages[imgnum]
                    break   
                elif answer == 'n':
                    # kill ds9 if the user hasn't already
                    if ds9.poll() == None:
                        ds9.kill()
                    return False
        if loadnew:
            continue

        print 'INFO\tfound coordinates of object as x: %s, y: %s' % (xcoo,ycoo)
        while True:
            answer = raw_input('QUERY\tare these coordinates correct? (y/n)\n')
            if answer == 'y': 
                objcoodone = True   
                break        
            elif answer == 'n':
                print 'INFO\tloading new image...'
                image = random.choice(subimages)
                imexamout = iraf.imexam(image,1,Stdout=1)
                objcoodone = False
                break
        if objcoodone:
            break
        
    # kill ds9 if the user hasn't already
    if ds9.poll() == None:
        ds9.kill()

    return '%s,%s' % (xcoo,ycoo)


def run_phot(image,coords,apertures,output,fwhm,sigma,datamin=0,datamax=60000,
             ccdread='readnois',readnoise=5,gain='gain',epadu=2.2,
             exposure='exptime',itime=1.0):
    """
    Wrapper to call iraf phot routine.
    """

    try:
        open(output)
    except IOError:
        pass
    else:
        os.remove(output)

    try:
        largeap = int(apertures)
    except ValueError:
        largeap = int(apertures.split(":")[1])
    finally:
        if largeap > 12:
            annulus = largeap + 3
        else:
            annulus = 15

    iraf.unlearn(iraf.datapars)
    iraf.datapars.fwhmpsf = fwhm
    iraf.datapars.sigma = sigma
    iraf.datapars.datamin = datamin
    iraf.datapars.datamax = datamax
    iraf.datapars.ccdread = ccdread
    iraf.datapars.gain = gain
    iraf.datapars.readnoise = readnoise
    iraf.datapars.epadu = epadu
    iraf.datapars.exposure = exposure
    iraf.datapars.itime = itime
    iraf.photpars.apertures = apertures

    iraf.unlearn(iraf.centerpars)
    iraf.centerpars.maxshift = 2.0

    iraf.unlearn(iraf.fitskypars)
    iraf.fitskypars.annulus = annulus

    iraf.unlearn(iraf.photpars)
    iraf.photpars.apertures = apertures
    
    try:


        photout = iraf.phot(image = image,
                            skyfile = "",
                            coord = coords,
                            output = output,
                            plotfile = "",
                            verify = "no",
                            interactive = "no",
                            verbose="yes",
                            Stdout = 1)
    except iraf.IrafError,e:
        raise "iraf.phot failed!\n",e
    logger.debug('phot output:\n'+\
                        '\n'.join(l for l in photout if l))


def run_mkapfile(photfiles,naperts,apercors,magfile="",
                 nparams=3):
    """
    Wrapper to call iraf mkapfile routine.
    """

    for f in (apercors,magfile):
        try:
            open(f)
        except IOError:
            pass
        else:
            os.remove(f)

    iraf.unlearn(iraf.mkapfile)
    iraf.mkapfile.magfile = magfile
    iraf.mkapfile.nparams = nparams
    iraf.mkapfile.interactive = "no"
        
    try:
        iraf.mkapfile(
                photfiles = photfiles,
                naperts = naperts,
                apercors = apercors)
    except iraf.IrafError,e:
        return e
    else:
        return None


