import os
import shutil
import subprocess
import logging
import atexit
from math import sqrt

import numpy as np
import pyfits

logger = logging.getLogger('run-subpipe.subpipe.myalardwrap')

# the file and directory path to this script, in case you call it from 
# another directory, so relative paths to the script are still intact
FILEPATH = os.path.realpath(__file__)
FILEDIR = os.path.dirname(FILEPATH)

def runsex(image,thresh=10,sat=55000,zp=25):

    daofindparam = os.path.join(FILEDIR,'Sex/daofind.param')
    defaultconv = os.path.join(FILEDIR,'Sex/default.conv')
    defaultnnw = os.path.join(FILEDIR,'Sex/default.nnw')
    configsex = os.path.join(FILEDIR,'Sex/config.sex')
    testcat = os.path.join(FILEDIR,'Sex/test.cat')

    defaultsex = os.path.join(FILEDIR,'Sex/default.sex')
    with open(defaultsex,'w') as f:
        f.write(get_sex_string(configsex,testcat,daofindparam,defaultconv,
                thresh,sat,zp,defaultnnw))

    subprocess.Popen([FILEDIR+'/Sex/sex',image,'-c',defaultsex],
    #subprocess.Popen(['sex',image,'-c',defaultsex],
                      stdout=open(os.devnull,'wb'),
                      stderr=subprocess.STDOUT).wait()
    try:
        open(testcat)
    except IOError:
        logger.error('SExtractor didn\'t work on the image. check data')
        return None

    starfile = os.path.splitext(image)[0]+'.stars'
    with open(starfile,'w') as f:
        try:
            p = subprocess.Popen(['sort','-n','-k','4',testcat],
                                 stdout=f).wait()
        except:
            pass 

    os.remove(defaultsex)
    os.remove(testcat)

    return starfile


def getmedianseeing(starlist):
    try:
        s = np.genfromtxt(starlist)
    except IOError:
        logger.warning('couldn\'t read from %s to obtain seeing info'
                       % starlist)
        return np.nan

    if len(s) == 0:
        logger.warning('SExtractor found no objects')
        return np.nan

    # remove elongated objects
    sa = s[s[:,7]<2]
    # remove objects with flags indicating various problems
    sb = sa[sa[:,4]==000]
    # fwhm must be +ve
    sc = sb[sb[:,8]>0]

    s = sc.copy()

    # get median seeing of images (in pixels)
    if len(s.shape) == 1:
        logger.warning('seeing based on only 1 SExtracted object')
        return float(s[8])
        
    medseeing = np.median(s[:,8])
    logger.info('median seeing = %5.3f (from %i measurements)'
                % (medseeing,len(s[:,8])))
    return float(medseeing)
    

def getseeingratio(starlist1,starlist2):

    try:
        s1 = np.genfromtxt(starlist1)
        s2 = np.genfromtxt(starlist2)
    except IOError:
        logger.warning('couldn\'t open output file from SExtractor')
        logger.info('SExtractor probably failed to find any objects')
        return np.nan
    if len(s1) == 0:
        logger.error('SExtractor found no objects in image!')
        logger.info('Incorrect alignment? check your WCS if using WREGISTER')
        return np.nan

    # remove elongated objects
    s1a = s1[s1[:,7]<2]
    s2a = s2[s2[:,7]<2]
    # remove objects with flags indicating various problems
    s1b = s1a[s1a[:,4]==000]
    s2b = s2a[s2a[:,4]==000]

    s1 = s1b.copy()
    s2 = s2b.copy()

    # detemine a ratio between the two (by directly comparing objects)
    ratio = []
    for i in range(len(np.atleast_2d(s1))):
        if len(ratio) > 100:
            break
        s1x = s1[i,0]
        s1y = s1[i,1]
        for j in range(len(np.atleast_2d(s2))):
            s2x = s2[j,0]
            s2y = s2[j,1]
            r = sqrt((s1x-s2x)**2+(s1y-s2y)**2)
            if r < 2:
                if s1[i,8] and s2[j,8]:
                    ratio.append(s1[i,8]/s2[j,8])
                    break
    logger.info('seeing ratio determined from median of %i object ratios'
                 % (len(ratio)))

    return np.median(ratio)
        
    
def runalard(template,image,tempsat=55000,imagesat=55000,imagethresh=25,
             tempthresh=25,
             nsx=9,nsy=9,sx=1,sy=1,minval=5,minstamp=130,kernelorder=2,
             reverseflag=0,hms=9,hss=0,sg1=0.7,sg2=1.5,sg3=2.5,
             deg_bg=1,removeconv=0,iterkernelsig=2,adapt=True,
             stamps=''):
    """
    Python function implementation of the perl script runalard.pl.
    Arguments correspond to same as in runalard.pl
    """
    
    baseimage = os.path.splitext(image)[0]
    basetemplate = os.path.splitext(template)[0]
    imstarlist = baseimage+'.stars'
    tempstarlist = basetemplate+'.stars'
    
    if not hss:
        hss = hms+6
    
    logger.info('determining better seeing frame')        
    try:
        os.remove(imstarlist)
    except OSError:
        pass
    finally:
        logger.debug('running SExtractor on aligned image') 
        runsex(image,imagethresh,imagesat)
    try:
        open(tempstarlist)
    except IOError:
        logger.debug('running SExtractor on template') 
        runsex(template,tempthresh,tempsat)

    logger.debug('getting seeing ratio of two frames') 
    ratio = getseeingratio(imstarlist,tempstarlist)
    if ratio < 1:
	    reverse = 0 # template worse than image
    elif ratio >= 1: 
	    reverse = 1 # template better than image
    elif np.isnan(ratio):
        logger.warning('failed to determine seeing ratio between frames!')
        logger.info('alignment incorrect or not enough point sources!')
        if reverseflag < 2:
            return None,ratio,None,None
        else:
            logger.info('subtraction direction was specified')
            logger.info('setting seeingratio to 0.000 as not required')
            ratio = 0.000
    r = 'image to template seeing ratio is %6.3f' % ratio

    logger.info(r)

    # remove the old STAMPS file if present and copy a new one if availible
    try:
        os.remove('STAMPS')
    except OSError:
        pass
    if stamps:
        stampsbyxy = 1
        shutil.copy(stamps,'STAMPS')
        logger.debug('stamps file copied')
    else:
        stampsbyxy = 0

    # get the median seeing of the image
    imageseeing = getmedianseeing(imstarlist)

    # if desired, let's try change ISIS params to reflect the seeing
    if adapt and imageseeing > 5: #TODO TESTING!
        cfg = [13,19,0.8,1.6,2.6]
        if imageseeing > 6:
            cfg = [15,21,0.9,1.7,3.0]
        if imageseeing > 7:
            cfg = [17,23,1.0,1.7,3.4]
        if imageseeing > 7.5:
            cfg = [19,25,1.0,1.8,3.5]
        if imageseeing > 8.5:
            cfg = [21,27,1.0,2.0,3.7]
        if imageseeing > 10:
            cfg = [23,29,1.0,2.5,4.3]
        hms,hss,sg1,sg2,sg3 = cfg
        logger.info('ISIS params adapted:\n'
                    '\t\thms=%i hss=%i sg1=%3.1f sg2=%3.1f sg3=%3.1f'
                    % (hms,hss,sg1,sg2,sg3))

    # dictate the direction of subtraction according to reverseflag provided
    if reverseflag == 1:
        reverse = abs(reverse-1)
    elif reverseflag == 2:
        reverse = 0
    elif reverseflag == 3:
        reverse = 1

    if reverse:
        tempsat,imagesat = imagesat,tempsat

    cfg = open('default_config','w')
    cfg.write("""
nstamps_x         %i       
nstamps_y         %i      
sub_x             %i       
sub_y             %i 
half_mesh_size    %i      
half_stamp_size   %i     
deg_bg            %i      
saturation1       %i   
saturation2       %i   
pix_min           %i 
min_stamp_center  %i  
ngauss            3       
deg_gauss1        6       
deg_gauss2        4       
deg_gauss3        2       
sigma_gauss1      %4.2f   
sigma_gauss2      %4.2f    
sigma_gauss3      %4.2f
deg_spatial       %i 
reverse           %i
stampsbyxy        %i
iter_kernal_sig   %i
""" % (nsx,nsy,sx,sy,hms,hss,deg_bg,imagesat,tempsat,minval,minstamp,
       sg1,sg2,sg3,kernelorder,reverse,stampsbyxy,iterkernelsig))
    cfg.close()
    alardfilename = baseimage+'.alardout'
    alardfile = open(alardfilename,'a')
    alardfile.write(r+'\n')

    if reverse:
        s=  'calling alardsub reverse = %s' % (reverse)
        logger.info(s)
        alardfile.write(s+'\n')
        alardfile.flush()
        alardcode = subprocess.Popen([os.path.join(FILEDIR,'Alard/alardsub'),
                                     template,image],stdout=alardfile).wait()
        try:
            shutil.move('conv.fits', baseimage+'.sub.fits')
        except OSError:
            logger.error('couldn\'t find ISIS subtracted output: "conv.fits"')
            return 0,0,0,alardcode
        if removeconv:
            os.remove('conv0.fits')
        else:
            shutil.move('conv0.fits',basetemplate+'.conv.fits')
            # copy header from template to convolved template
            templatehdr = pyfits.getheader(template)
            convHDU = pyfits.open(basetemplate+'.conv.fits',mode='update')
            convHDU[0].header = templatehdr
            convHDU.flush()
            convHDU.close()

    else:
        s=  'calling alardsub reverse = %s' % (reverse)

        logger.info(s)
        alardfile.write(s+'\n')
        alardfile.flush()
        alardcode = subprocess.Popen([os.path.join(FILEDIR,'Alard/alardsub'),
                                     image,template],stdout=alardfile).wait()
        try:
            shutil.move('conv.fits', baseimage+'.sub.fits')
        except OSError:
            logger.error('couldn\'t find ISIS subtracted output: "conv.fits"')
            return 0,0,0,alardcode
        if removeconv:
            os.remove('conv0.fits')
        else:
            shutil.move('conv0.fits',baseimage+'.conv.fits')
            # copy header from image to convolved image
            imagehdr = pyfits.getheader(image)
            convHDU = pyfits.open(baseimage+'.conv.fits',mode='update')
            convHDU[0].header = imagehdr
            convHDU.flush()
            convHDU.close()

    alardfile.close()
    logger.info('ISIS output located in %s' % os.path.basename(alardfilename))

    # use the value of 'sum_kernel' to deduce if subtraction went well
    # (should be of order 1 for same filter/exposure observations)
    try:
        os.remove(baseimage+'.sum_kernel')
    except OSError:
        pass
    try:
        shutil.move('sum_kernel',baseimage+'.sum_kernel')
    except IOError:
        logger.error('no sum_kernel file - subtraction gone awry')
        logger.info('check your parameters in your ISIScfg.py file')
        return 0,0,np.nan,alardcode
    try:
        with open(baseimage+'.sum_kernel') as sk:
            sum_kernel = float(sk.readline().split()[-1])
    except IndexError:
        logger.error('couldn\'t deduce value of sum_kernel!')
        sum_kernel = -1

    return reverse,ratio,sum_kernel,alardcode

def get_sex_string(configsex,testcat,daofindparam,defaultconv,thresh,sat,
                   zp,defaultnnw):
    with open(configsex) as cfgsex:
        configstring = cfgsex.read()
    return configstring.format(testcat,daofindparam,thresh,thresh,
                               defaultconv,sat,zp,defaultnnw)

@atexit.register
def cleanup():
    for junk in ['conv.fits','conv0.fits','default_config','kernel_table',
                 'toto.bmp']:
        try:
            os.remove(junk)
        except OSError:
            pass


