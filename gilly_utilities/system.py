from __future__ import print_function

import sys
import os
import shutil
import threading
import errno
import signal
import logging
import collections
import warnings
from datetime import datetime

if getattr(sys.version_info, 'major') == 2:
    import urllib2
elif getattr(sys.version_info, 'major') == 3:
    import urllib.request as urllib2
else:
    raise ImportError("Unable to detect the version of python you are using!")

# Compatability for python3
if getattr(sys.version_info, 'major') == 3:
	xrange = range

import numpy as np
import pandas as pd

from .extras import cprint
import gilly_utilities.datetime64
import gilly_utilities.manipulation

class DelayedKeyboardInterrupt(object):
    """Forces an operation to complete when this class function is called before an 
    operation. Handles Ctrl+C, Ctrl+Z and Ctrl+\ keyboard interrupts.
    
    Example
    -------
    
    with DelayedKeyboardInterrupt():
        for i in xrange(10):
            print(i)
            systime.sleep(1)
            
    >>> 0
    >>> 1
    >>> ^C[Warning] Please wait until the current operation has finish
    >>> ^Z[Warning] Please wait until the current operation has finish
    >>> ^\[Warning] Please wait until the current operation has finish
    >>> 2
    ...
    >>> 10
    >>> KeyboardInterrupt
    
    Reference
    ---------
    https://stackoverflow.com/a/21919644/8765762
    """    
    
    def __enter__(self):
        self.signal_received = False
        self.ctrlc_handler = signal.signal(signal.SIGINT, self.handler)
        self.ctrlz_handler = signal.signal(signal.SIGTSTP, self.handler)
        self.ctrlslash_handler = signal.signal(signal.SIGQUIT, self.handler)
        
    def handler(self, sig, frame):
        self.signal_received = (sig, frame)
        logging.debug('SIGINT received. Delaying KeyboardInterrupt.')
        cprint("[Warning] Please wait until the current operation has finished", type='warning')
        
    def __exit__(self, type, value, traceback):
        signal.signal(signal.SIGINT, self.ctrlc_handler)
        if self.signal_received:
            self.ctrlc_handler(*self.signal_received)
            
        signal.signal(signal.SIGTSTP, self.ctrlz_handler)
        if self.signal_received:
            self.ctrlz_handler(*self.signal_received)
            
        signal.signal(signal.SIGQUIT, self.ctrlslash_handler)
        if self.signal_received:
            self.ctrlslash_handler(*self.signal_received)

class unbuffered(object):
    """Forces the print statements to be written without the need for flushing. Useful for
    sending print statements to text files when running python on a cluster.
    
    Usage
    -----
    import sys
    import gilly_utilities as gu

    sys.stdout = gu.unbuffered(sys.stdout)
    
    Reference
    ---------
    https://stackoverflow.com/a/107717/8765762
    """
    
    def __init__(self, stream):
        self.stream = stream
    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
    def writelines(self, datas):
        self.stream.writelines(datas)
        self.stream.flush()
    def __getattr__(self, attr):
        return getattr(self.stream, attr)

class antiverbose(object):
    """Suppresses the output of the sys.stdout.write and so no output
    will be visible on the console.
    
    To use this class place in code like so,
    
    with gu.antiverbose():
        ...
        
    ...
    
    References
    ----------
    https://stackoverflow.com/a/8391735/8765762
    https://stackoverflow.com/a/45669280/8765762
    """
    
    def __init__(self, verbose=False):
        """
        Specify whethere you want to turn on print statements or not
        """
        
        self.verbose = verbose
        
    def __enter__(self):
        
        if not self.verbose:
            self._original_stdout = sys.stdout
            sys.stdout = open(os.devnull, 'w')
            
    def __exit__(self, type, value, traceback):
    
        if not self.verbose:
            sys.stdout.close()
            sys.stdout = self._original_stdout

def verbose_class(func):
    """
    This decorator can be used to suppress the output of all stdout
    inside a class function. To toggle this function you need to set
    self.verbose as either True or False.
    
    Example
    -------
    >>> class fun(object):
    
    >>>     def __init__(self, verbose=False):
            self.verbose = verbose
            return
        
    >>> @dec_verbose_class
    >>> def func(self):
    >>>     print("Hello")
        
    >>> bob = fun(True)
    >>> bob.func()
    "Hello"
    >>> bob = fun(False)
    >>> bob.func()
    >>> 
    
    References
    ----------
    https://stackoverflow.com/a/5929165/8765762
    https://stackoverflow.com/a/7590709/8765762
    """
    
    def wrapper(self, *args, **kwargs):
        if not self.verbose:
        
            # block all printing to the console
            sys.stdout = open(os.devnull, 'w')
            # call the method in question
            value = func(self, *args, **kwargs)
            # enable all printing to the console
            sys.stdout = sys.__stdout__
            # pass the return value of the method back
            return value
        
        else:
            return func(self, *args, **kwargs)
    return wrapper

def isarray(arg):
    """Checks whether arg is array_like (e.g. tuple, list, np.ndarray, etc.)"""
    
    #return type(arg) is not str and isinstance(arg, collections.Sequence)
    
    dtypes = [list, tuple, np.ndarray, pd.DataFrame]
    return np.any([isinstance(arg, dtype) for dtype in dtypes])

def isnumeric(arg, warn=True):
    """
    Test element-wise for numerics (e.g. 2.4, 2).

    The result is returned as a boolean array.
    """
    
    # Force arg to be a numpy array
    arg = np.atleast_1d(arg)
    
    # Check for finitness
    try:
        return np.isfinite(arg)
    except TypeError:
        if warn is True:
            warnings.warn("[gu.isnumeric] invalid data type found in arg. Returning False", UserWarning, stacklevel=2)
        return np.array(False)

def isnone(arg, keepshape=True):
    """
    Test element-wise for nones.

    The result is returned as a boolean array.
    """

    # Force arg to be a numpy array
    arg = np.atleast_1d(arg)
    nones_full = np.zeros(arg.shape, dtype=bool)
    
    # Create index array of arg to reorganise after we need to flatten arg
    index = np.arange(arg.size).reshape(arg.shape)
    
    # Flatten arg array
    arg = np.hstack(arg.flat)
    index_flat = np.hstack(index)
    
    # Check for nones
    nones = np.array([val is None for val in arg], dtype=bool)
    
    if keepshape is True:
        
        # Return a restructured array
        for ind, val in zip(index_flat, nones):
            nones_full[np.where(index == ind)] = val
        
        return nones_full
    
    else:
        return nones

def iszero(arg, keepshape=True):
    """
    Test element-wise for zeros.
    
    The result is returned as a boolean array.
    """
    
    # Force arg to be a numpy array
    arg = np.atleast_1d(arg)
    zero_full = np.zeros(arg.shape, dtype=bool)
    
    # Create index array of arg to reorganise after we need to flatten arg
    index = np.arange(arg.size).reshape(arg.shape)
    
    # Flatten arg array
    arg = np.hstack(arg.flat)
    index_flat = np.hstack(index)
    
    # Check for zeros
    zeros = np.array([val == 0 for val in arg], dtype=bool)
    
    if keepshape is True:
        
        # Return a restructured array
        for ind, val in zip(index_flat, zeros):
            zero_full[np.where(index == ind)] = val
        
        return zero_full
    
    else:
        return zeros
        
def isval(arg, value, keepshape=True):
    """
    Test element-wise for specific value.
    
    The result is returned as a boolean array.
    """
    
    # Force arg to be a numpy array
    arg = np.atleast_1d(arg)
    zero_full = np.zeros(arg.shape, dtype=bool)
    
    # Check if arg has any data
    if arg.size == 0:
        return False
    
    # Create index array of arg to reorganise after we need to flatten arg
    index = np.arange(arg.size).reshape(arg.shape)
    
    # Flatten arg array
    arg = np.hstack(arg.flat)
    index_flat = np.hstack(index)
    
    # Check for zeros
    zeros = np.array([val == value for val in arg], dtype=bool)
    
    if keepshape is True:
        
        # Return a restructured array
        for ind, val in zip(index_flat, zeros):
            zero_full[np.where(index == ind)] = val
        
        return zero_full
    
    else:
        return zeros
    
"""
Works out the length of string arrays element-wise

Reference
---------
https://stackoverflow.com/a/44587916/8765762
"""
arrlen = np.vectorize(len)
    
def ensure_dir(dirname, dir_or_file='dir'):
    """Ensure that a named directory exists; if it does not, attempt to create it.
    
    Sources
    -------
    http://stackoverflow.com/a/21349806
    """

    # Copy dirname to return to user
    dirname_return = dirname

    try:
        os.makedirs(dirname) if dir_or_file == 'dir' else os.makedirs(os.path.dirname(dirname))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    return dirname

def del_folder(folder, sub=False): 
    """Deletes a folder. Option sub to make recursive"""

    for the_file in os.listdir(folder):
        file_path = os.path.join(folder, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path) and sub == True: 
                shutil.rmtree(file_path)
        except Exception as e:
            print(e)
            
def Print_Output(delay_time, t_start, it_tot, it):
  t = threading.Timer(delay_time, Print_Output(delay_time, t_start, it_tot, it)).start()
  os.system('cls' if os.name=='nt' else 'clear')
  print("Time Left (s): ", "%.0f" % ((it_tot-it)*((time.time()-t_start)/it)))
  print("Events Left: ", it_tot-it)

def file_checker(dates, date_range, files=None, file_size_min=0, yes_file=1,
        no_file=0, corrupt_file=2):
    """Checks the availability of files
    
    Parameters
    ----------
    dates : numpy object array
        An array of datetimes corresponding to each file location in files.
    date_range : nump object array
        An array over the list of dates you want to test.
    files : numpy array
        A list of file locations to be tested
    file_size_min : int, optional
        The minimum file size (in bytes) required to be valid. This is useful for files that
        exist but don't contain any data.

    Returns
    -------
    File_Availability : list
        A boolean list with 1 for file exists and is above the minimum file size threshold
        and zero for either file doesn't exist or file is below or equal to minimum file
        threshold.        
    """
    
    # if files are not specified, then only check dates occur in dates range.
    # This method is much quicker, as you can use numpy element-wise
    # operations and don't have to check file size of every file.
    if files is None:
        # Create zero array matching date_range length
        File_Availability = np.zeros(date_range.size)
        
        # If date is found in date_range then set File_Availability to 1
        File_Availability[np.in1d(date_range, dates)] = 1
        
        # Return data
        return File_Availability
    else:
        # Create zero array matching date_range length
        File_Availability = np.zeros(date_range.size)
        File_Availability = []
        for i in xrange(date_range.shape[0]):
            if np.sum(dates == date_range[i]) == 1:            
                if os.stat(files[dates == date_range[i]][0]).st_size > file_size_min:
                    File_Availability.append(yes_file)
                else:
                    File_Availability.append(corrupt_file)
            else:
                File_Availability.append(no_file)
                
        return np.array(File_Availability, dtype=float)

def file_checker2(dates, date_range, files=None, file_size_min=0, yes_file=1,
        no_file=0, corrupt_file=2):
    """Checks the availability of files
    
    Parameters
    ----------
    dates : numpy object array
        An array of datetimes corresponding to each file location in files.
    date_range : nump object array
        An array over the list of dates you want to test.
    files : numpy array
        A list of file locations to be tested
    file_size_min : int, optional
        The minimum file size (in bytes) required to be valid. This is useful for files that
        exist but don't contain any data.

    Returns
    -------
    File_Availability : list
        A boolean list with 1 for file exists and is above the minimum file size threshold
        and zero for either file doesn't exist or file is below or equal to minimum file
        threshold.        
    """

    # Create zero array matching date_range length
    File_Availability = np.zeros(date_range.size)
    
    # Get mask for dates in date_range
    mask_date = np.in1d(date_range, dates)

    # If date is found in date_range then set File_Availability to yes_file
    File_Availability[mask_date] = yes_file
        
    # if files are not specified, then only check dates occur in dates range.
    # This method is much quicker, as you can use numpy element-wise
    # operations and don't have to check file size of every file.
    if files is not None:

        # Get file size for all files
        file_sizes = []
        for file in files:
            try:
                file_sizes.append(os.stat(file).st_size)
            except OSError:
                file_sizes.append(0)
        
        # Convert to numpy array to use element-wise ops.
        file_sizes = np.array(file_sizes)
        
        # Test which files are smaller than expected
        mask_filesize = file_sizes <= file_size_min

        # Get date_range for dates that have files too small
        mask_datesfile = np.in1d(date_range, dates[mask_filesize])

        # Combine mask_filesize with mask_date
        File_Availability[mask_datesfile] = corrupt_file
    
    # Return data
    return File_Availability
    
def File_Aligner_NoSize(files, dates, date_range):
    """Checks the availability of files
    
    Parameters
    ----------
    files : numpy array
        A list of file locations to be tested
    dates : numpy object array
        An array of datetimes corresponding to each file location in files.
    date_range : nump object array
        An array over the list of dates you want to test.
    file_size_min : int, optional
        The minimum file size (in bytes) required to be valid. This is useful for files that
        exist but don't contain any data.

    Returns
    -------
    File_Availability : list
        A boolean list with 1 for file exists and is above the minimum file size threshold
        and zero for either file doesn't exist or file is below or equal to minimum file
        threshold.        
    """
    
    File_Date = np.zeros(date_range.shape[0], dtype=object)
    File_Loc = np.zeros(date_range.shape[0], dtype='S256')
    for i in xrange(date_range.shape[0]):
        if np.sum(dates == date_range[i]) >= 1:            
            File_Date[i] = date_range[i]
            File_Loc[i] = files[dates == date_range[i]][0]
            
    return np.array(File_Loc, dtype='S256'), np.array(File_Date, dtype=object)
    
def File_Aligner(files, dates, date_range, file_size_min=0):
    """Checks the availability of files
    
    Parameters
    ----------
    files : numpy array
        A list of file locations to be tested
    dates : numpy object array
        An array of datetimes corresponding to each file location in files.
    date_range : nump object array
        An array over the list of dates you want to test.
    file_size_min : int, optional
        The minimum file size (in bytes) required to be valid. This is useful for files that
        exist but don't contain any data.

    Returns
    -------
    File_Availability : list
        A boolean list with 1 for file exists and is above the minimum file size threshold
        and zero for either file doesn't exist or file is below or equal to minimum file
        threshold.        
    """
    
    File_Date = np.zeros(date_range.shape[0], dtype=object)
    File_Loc = np.zeros(date_range.shape[0], dtype='S256')
    for i in xrange(date_range.shape[0]):
        if np.sum(dates == date_range[i]) == 1:    
            if os.stat(files[dates == date_range[i]][0]).st_size > file_size_min:
                File_Date[i] = date_range[i]
                File_Loc[i] = files[dates == date_range[i]][0]
            else:
                File_Date[i] = 2
                File_Loc[i] = 2
            
    return np.array(File_Loc, dtype='S256'), np.array(File_Date, dtype=object)
    
def urllib_authentication(url, username, password, library='urllib2'):
    """
    When using urllib2 on websites which require authentication. This
    function can be used to access the website
    """
    
    p = urllib2.HTTPPasswordMgrWithDefaultRealm()

    p.add_password(None, url, username, password)

    handler = urllib2.HTTPBasicAuthHandler(p)
    opener = urllib2.build_opener(handler)
    urllib2.install_opener(opener)
    
    return