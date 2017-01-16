# Some variables to be defined for use by subpipe

###############
# IMAGE HEADERS
###############
# required per image (i.e. these header fields must exist for each image)
EXPHDR = "exptime"      # float [seconds]

# potentially only one value required per run 
# we'll try to use the value in the header key given, unless it doesn't exist- 
# then we'll use the constant value given below for all images
OBJECTHDR = "object"        # name of object being observed
OBJECTNAME = "myobject"     # string
GAINHDR = "gain"            # gain of detector
GAIN = 2.0                  # float [e per adu]
RDNOISEHDR = "readnois"     # readnoise of detector
RDNOISE = 5.0               # float [counts]
 
# the pipeline will attempt to determine a FWHM estimate using Sextractor.
# if this fails it will default to this value:
FWHMDEFAULT = 3.5       # float [pixels]

# list of observation date headers, at least one of these must be a float 
# (i.e. '123.456'), otherwise date will default to 1.0. first key
# in each header sucessfully matching a float will be used.
# (affects photometry -- lightcurve creation -- only)
DATEKEYS = ["jd","mjd","jd-obs","mjd-obs","obsjd","obsmjd"]
# list of filter headers, one of which should contain the observation filter
# (any header keys whose value is `clear` or null are ignored)
# first key in each header with an acceptable value will be used
FILTERKEYS = ["filter","filters","filter1","filter2","wffband"]
###################
# END IMAGE HEADERS
###################

# the min/max number of objects to find with SExtractor
# must be appropriate values for your data
TEMPMINOBJ = 20
TEMPMAXOBJ = 85
IMAGEMINOBJ = 20
IMAGEMAXOBJ = 85

# the initial threshold to begin object finding with SExtractor
# it will be altered to satisfy the restrictions on number of objects above
IMAGETHRESH = 25
TEMPTHRESH = 25

# saturation limit used by SExtractor and cosmic ray removal
# being a bit conservative probably works best
IMAGESATLIMIT = 55000
TEMPSATLIMIT = 55000

# the limits of sum_kernel (see ISIS code for description)
# if the value falls outside these limits, the  subtraction is deemed to be
# incorrect and is ran in reverse
# if the pipeline is incorrectly entering reverse, loosening these 
# restrictions will prevent it (check sum_kernel values in subpipe_report.txt)
# for two images in the same band of the same exposure this should be of order
# 1 - it ill vary further if subtracting different filter/exposure images
# NB these are only checked if your reverse parameter is 0 or 1
# (if 2 or 3 you are telling the pipeline explicitly which direction to use
#  and so it doesn't bother checking if you made the best guess)
MAXSUMKERNEL = 28
MINSUMKERNEL = 0.0

# alignment methods to try
# at least one must be true for any alignment, if all equate to false, the
# pipeline assumes they are prealigned and will skip alignment
XYXYMATCH = True
WREGISTER = False

# XYXYMATCH params (see iraf.xyxymatch help for info)
XYTOL = 3               # tolerance
XYNMATCH = 60           # nmatch (CPU time can rocket if this is too high)
                        # if number of objects is high, increase this
XYSEP = 5               # (minimum) separation between coordinates to use
XYMIN = 5               # minimum number of matched coordinates in order to
                        # accept the transformation solution
SEARCHRAD = 25          # if xyxymatch fails the first time, it will reduce 
                        # the coordinate list in the image to only objects
                        # that have a corresponding template object detected
                        # within this number of pixels. this will help if the
                        # images are only slightly misaligned, to skip (i.e.
                        # when images are significantly misaligned) set to 0.

