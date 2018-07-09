'''
.. module: beta
Created on 27 May 2013

@author: awegsche, vimaier

@version: 2016.11.p2

GetLLM.algorithms.beta.py stores helper functions for phase calculations for GetLLM.
This module is not intended to be executed. It stores only functions.


'''
import sys
import math
from math import sqrt
import traceback
import re
import multiprocessing
import time

from copy import deepcopy
import numpy as np
from numpy import sin, tan
import pandas as pd

from scipy.linalg import circulant
import Python_Classes4MAD.metaclass
import utils.bpm
#from GetLLM.GetLLMError import GetLLMError
import compensate_excitation
from constants import PI, TWOPI
from model.accelerators.accelerator import AccExcitationMode
from utils import tfs_pandas
from utils import logging_tools

__version__ = "2018.5.a"

DEBUG = sys.flags.debug  # True with python option -d! ("python -d GetLLM.py...") (vimaier)
PRINTTIMES = False
LOGGER = logging_tools.get_logger(__name__)

if DEBUG:
    import debug_algorithms as DBG

#--- Constants

DEFAULT_WRONG_BETA      = 1000                      #@IgnorePep8
EPSILON                 = 0#1.0E-16                 #@IgnorePep8
ZERO_THRESHOLD          = 1e-3                      #@IgnorePep8
COT_THRESHOLD           = 15.9
RCOND                   = 1.0e-10                    #@IgnorePep8

BOXLENGTH               = 50                        #@IgnorePep8
BOXINDENT               =  4                        #@IgnorePep8
CALCULATE_BETA_HOR = True
CALCULATE_BETA_VER = True

# --------------- Column Indices :

INDX_NAME   = 0
INDX_S      = 1
INDX_BET    = 2
INDX_BETSTAT= 3
INDX_BETSYS = 4
INDX_BETERR = 5
INDX_ALF    = 6
INDX_ALFSTAT= 7
INDX_ALFSYS = 8
INDX_ALFERR = 9
INDX_CORR   = 10
INDX_BETMDL = 11
INDX_BETBEAT= 12
INDX_NCOMB  = 13

# --------------- Errors method
METH_IND        = -1
METH_3BPM       = 0
METH_A_NBPM     = 1
METH_MC_NBPM    = 2

ID_TO_METHOD = {
    METH_3BPM:"3BPM method",
    METH_A_NBPM:"Analytical N-BPM method"}

#---------------------------------------------------------------------------------------------------
#--- classes
#---------------------------------------------------------------------------------------------------


class MeasuredValues:
    '''
    class that stores information about the calculated alpha and beta values
    '''
    def __init__(self, alfa, beta, string="", use_it=False):
        self.beta = beta
        self.alfa = alfa
        self.patternstring = string
        self.use_it = use_it

class BetaData(object):
    """ File for storing results from beta computations. """

    def __init__(self):
        self.x_phase = None  # beta x from phase
        self.x_phase_f = None  # beta x from phase free
        self.y_phase = None  # beta y from phase
        self.y_phase_f = None  # beta y from phase free

        self.x_amp = None  # beta x from amplitude
        self.y_amp = None  # beta y from amplitude

        self.x_ratio = 0  # beta x ratio
        self.x_ratio_f = 0  # beta x ratio free
        self.y_ratio = 0  # beta x ratio
        self.y_ratio_f = 0  # beta x ratio free


ID_INVALID = 0
IDQUAD = 1
IDSEXT = 2
IDBPM = 3
IDDIPL = 4

MAINFIELD = {
    IDQUAD:"K1L",
    IDSEXT:"K2L",
    IDDIPL:"K0L"}

def gettype(_type):
    if _type == "QUAD":
        return IDQUAD
    elif _type == "SEXT":
        return IDSEXT
    elif _type == "BPM":
        return IDBPM
    elif _type == "DIPL":
        return IDDIPL
    _warning_("-<-<-<-<-< INVALID UncertaintyDefinition type  '{:s}' -<-<-<-<-<-<-<-<".format(_type))
    return ID_INVALID

class UncertaintyDefinition:
    def __init__(self, _pattern, _dk1=0, _ds=0, _dx=0, _type="QUAD"):
        self.pattern = _pattern
        self.dX = _dx
        self.dS = _ds
        self.dK1 = _dk1
        self.type = gettype(_type)


        def settype(self, _type):
         self.type = gettype(_type)


class UncertaintyDefinitionRE:
    def __init__(self, _pattern, _dk1=0, _ds=0, _dx=0, _type="QUAD"):
        self.pattern = re.compile(_pattern)
        self.dX = _dx
        self.dS = _ds
        self.dK1 = _dk1
        self.type = gettype(_type)
        self.tas = _type

    def settype(self, _type):
        self.type = gettype(_type)

    def match(self, string):
        return self.pattern.match(string)

    def to_string(self):
        return "/{:s}/ dK1={:g}, dS={:g}, dX={:g}, {:6s}".format(self.pattern.pattern, self.dK1, self.dS, self.dX,
                                                                 self.tas)
class UncertaintyInformation:
    def __init__(self, _name, _bet, _betend, _mu, _muend, _dk1, _k1l, _k1lend, _k2l, _dx, _ds, _debug):
        self.name = _name
        self.bet = _bet
        self.betend = _betend
        self.mu = _mu
        self.muend = _muend
        self.dk1 = _dk1
        self.k1l = _k1l
        self.k1lend = _k1lend
        self.k2l = _k2l
        self.dx = _dx
        self.ds = _ds
        self.debug = _debug


class ErrorFile:
    def __init__(self):
        self.indx = {}
        self.elements = None
        self.size = 0
        self.names = []

    def add(self, uni):
        if self.elements is None:
            self.elements =  [0.0, uni.bet, uni.betend, uni.mu, uni.muend, uni.dk1, uni.k1l, uni.k1lend, uni.k2l, uni.dx, uni.ds],
        else:
            self.elements = np.concatenate(
                (self.elements,
                 ([0.0, uni.bet, uni.betend, uni.mu, uni.muend, uni.dk1, uni.k1l, uni.k1lend, uni.k2l, uni.dx, uni.ds],))
                                           )
        self.size = len(self.elements)
        self.indx[uni.name] = self.size - 1
        self.names.append(uni.name)
#         print "{:12s}, at index {:d} {:6.1f} {:6.1f} {:5.1f} {:5.1f} {:12.3e} {:12.3e} {:9.4f} {:9.4f} {:9.4f} {:9.4f}".format(
#             uni.name, self.size, uni.bet, uni.betend, uni.mu, uni.muend, uni.dk1, uni.k1l, uni.k1lend, uni.k2l, uni.dx, uni.ds

class Uncertainties:  # error definition file

    def __init__(self):
        self.version = "1"
        self.keys = []
        self.regex = []
        self.properties = {}

    def open(self, filename):
        _debug_("opening error definition file '{:s}'".format(filename))
        with open(filename, "r") as F:

            line = F.readline()

            if line.strip() == "version 2":
                line = F.readline()
                for line in F:

                    line = re.split("//", line)[0].strip()  # separating code from comments
                    if len(line) == 0:
                        continue
                    match = re.search(r'prop (\w+)\s+=\s(\w[\w\s]*)', line)
                    if match is not None:
                        _debug_("adding {} = {} to properties".format(match.group(1), match.group(2)))
                        self.properties[match.group(1)] = match.group(2).strip()
                    else:
                        words = re.split(r'\s', line)

                        if words[0].startswith("re:"):
                            ud = UncertaintyDefinitionRE(words[0].split(":")[1])

                            for word in words:
                                kv = word.split("=")
                                if kv[0] == "dK1":
                                    ud.dK1 = float(kv[1])
                                elif kv[0] == "dS":
                                    ud.dS = float(kv[1])
                                elif kv[0] == "dX":
                                    ud.dX = float(kv[1])
                                elif kv[0] == "Type":
                                    ud.settype(kv[1])
                            self.regex.append(ud)
                        else:
                            ud = UncertaintyDefinition(words[0])

                            for word in words:
                                kv = word.split("=")
                                if kv[0] == "dK1":
                                    ud.dK1 = float(kv[1])
                                elif kv[0] == "dS":
                                    ud.dS = float(kv[1])
                                elif kv[0] == "dX":
                                    ud.dX = float(kv[1])
                                elif kv[0] == "Type":
                                    ud.settype(kv[1])
                            self.keys.append(ud)

                return True
            else:

                try:
                    definitions = Python_Classes4MAD.metaclass.twiss(filename)

                except:
                    _error_("loading errorfile didn't work")
                    _error_("errordefspath = {0:s}".format(filename))
                    return False

                _debug_("error definitions file version 1")
                self.properties["RELATIVE"] = definitions.RELATIVE
                self.properties["RADIUS"] = definitions.RADIUS

                for index in range(len(definitions.PATTERN)):
                    pattern = definitions.PATTERN[index]
                    self.regex.append(UncertaintyDefinitionRE(
                        pattern,
                        definitions.dK1[index],
                        definitions.dS[index],
                        definitions.dX[index],
                        definitions.MAINFIELD[index]))
                return True


    def create_errorfile(self, twiss_full, twiss_full_centre):
        '''
        Adds uncertainty information to twiss_full.

        :Sources of Errors:
            dK1:    quadrupolar field errors
            dS:     quadrupole longitudinal misalignments
            dX:     sextupole transverse misalignments
            BPMdS:  BPM longitudinal misalignments
        '''

        _debug_("Start creating uncertainty information")

        # create new columns, fill MUX/Y_END and BETX/Y_END
        #twiss_full.loc[:]["MUX_END"] = np.roll(twiss_full.loc[:]["MUX"], 1)
        #twiss_full.loc[:]["MUY_END"] = np.roll(twiss_full.loc[:]["MUY"], 1)
        #twiss_full.loc[:]["BETX_END"] = np.roll(twiss_full.loc[:]["BETX"], 1)
        #twiss_full.loc[:]["BETY_END"] = np.roll(twiss_full.loc[:]["BETY"], 1)
        twiss_full["UNC"] = False
        twiss_full["dK1"] = 0
        twiss_full["KdS"] = 0
        twiss_full["mKdS"] = 0
        twiss_full["dX"] = 0
        twiss_full["BPMdS"] = 0

        # loop over uncertainty definitions, fill the respective columns, set UNC to true
        for reg in self.regex:
            _debug_("creating uncertainty information for RegEx {:s}".format(reg.to_string()))
            reg_mask = twiss_full.index.str.match(reg.pattern)
            twiss_full.loc[reg_mask, "dK1"] = (reg.dK1 * twiss_full.loc[reg_mask, "K1L"]) **2
            twiss_full.loc[reg_mask, "dX"] = reg.dX**2
            if reg.type == IDBPM:
                twiss_full.loc[reg_mask, "BPMdS"] = reg.dS**2
            else:
                twiss_full.loc[reg_mask, "KdS"] = (reg.dS * twiss_full.loc[reg_mask, "K1L"]) **2
            twiss_full.loc[reg_mask, "UNC"] = True

        # in case of quadrupole longitudinal misalignments, the element (DRIFT) in front of the
        # misaligned quadrupole will be used for the thin lens approximation of the misalignment
        twiss_full["mKdS"] = np.roll(twiss_full.loc[:]["KdS"], 1)
        twiss_full.loc[:]["UNC"] |= np.roll(twiss_full.loc[:]["UNC"], 1)

        # dump the modified twiss_full and return it to the beta calculation
        _info_("DONE creating uncertainty information")
        #_debug_("dumping new twiss_full.dat")
        #tfs_pandas.write_tfs(os.path.join("/dump_twiss_full"), twiss_full, {})
        return twiss_full[twiss_full["UNC"] == True]

#---------------------------------------------------------------------------------------------------
# main part
#---------------------------------------------------------------------------------------------------


def _write_getbeta_out(number_of_bpms, range_of_bpms, phase_f, data, model, error_method, bpms, tfs_file,
                       _plane_char, union, dpp=0, dppq1=0):
    '''
    Writes the file ``getbeta<x/y>.out``.

    :Parameters:
        q1, q2
            tunes
        number_of_bpms
            number of bpm combinations to keep for Monte Carlo N-BPM method
        range_of_bpms
            range of BPMs from which the combinations are taken
        beta_d_col
            no idea
        data
            the result of the method
        rmsbbx
            RMS beta beating
        error_method
            the ID of the used error method
        tfs_file
            the tfs file to which the results will be written
    '''

    LOGGER.debug("Writing beta from phase results")

    tfs_file.add_header("DPP", dpp)
    tfs_file.add_header("BetaAlgorithmVersion", __version__)
    tfs_file.add_header("ErrorsFrom", ID_TO_METHOD[error_method])
    tfs_file.add_header("RCond", RCOND)

    if error_method == METH_3BPM:
        tfs_file.add_header("NumberOfBPMs", 3)
        tfs_file.add_header("RangeOfBPMs", 5)
    else:
        tfs_file.add_header("NumberOfBPMs", number_of_bpms)
        tfs_file.add_header("RangeOfBPMs", range_of_bpms)

    beta_df = pd.DataFrame(data=data, index=bpms.index)
    beta_df["NFILES"] = bpms.loc[:, "NFILES"]
    beta_df["BET" + _plane_char + "MDL"] = model.loc[beta_df["NAME"], "BET" + _plane_char]
    beta_df["BBEAT"] = beta_df["BET" + _plane_char] / beta_df["BET" + _plane_char + "MDL"] - 1

    rmsbb = np.sqrt(np.mean(beta_df["BBEAT"] * beta_df["BBEAT"]))
    _info_("RMS betabeat: {:.2f}%".format(rmsbb * 100))
    tfs_file.add_header("RMSbetabeat", rmsbb)

    for bpm in bpms.index:
        phase_f[bpm] = [
            beta_df.loc[bpm, "BET" + _plane_char],
            beta_df.loc[bpm, "SYSBET" + _plane_char],
            beta_df.loc[bpm, "STATBET" + _plane_char],
            beta_df.loc[bpm, "ERRBET" + _plane_char]
        ]
    tfs_file.set_dataframe(beta_df.loc[beta_df["NCOMB"] > -2])
    return beta_df


def calculate_beta_from_phase(getllm_d, twiss_d, tune_d, phase_d,
                              files_dict):
    '''
    Calculates beta from phase using either the 3-BPM or N-BPM method.
    Fills the following TfsFiles:
        ``getbetax.out        getbetax_free.out        getbetax_free2.out``
        ``getbetay.out        getbetay_free.out        getbetay_free2.out``

    :Parameters:
        'getllm_d': _GetllmData (In-param, values will only be read)
            lhc_phase, accel and beam_direction are used.
        'twiss_d': _TwissData (In-param, values will only be read)
            Holds twiss instances of the src files.
        'tune_d': _TuneData (In-param, values will only be read)
            Holds tunes and phase advances
        'phase_d': _PhaseData (In-param, values will only be read)
            Holds results from get_phases
    '''
    # setting up
    beta_d = BetaData()
    accelerator = getllm_d.accelerator

    # selecting models -----------------------------------------------------------------------------

    free_model = accelerator.get_model_tfs()
    elements = accelerator.get_elements_tfs()
    # there are functions that are written to take both, for the future (?)
    elements_centre = elements

    # the following tries to get the best_knowledge model
    # if it doesn't find it, it takes the base model
    try:
        free_bk_model = accelerator.get_best_knowledge_model_tfs()
    except AttributeError:
        free_bk_model = free_model

    driven_model = None
    if accelerator.excitation != AccExcitationMode.FREE:
        # in the case of driven motion, we need the driven model as well
        driven_model = accelerator.get_driven_tfs()

    if getllm_d.union:
        commonbpms_x = twiss_d.zero_dpp_unionbpms_x
        commonbpms_y = twiss_d.zero_dpp_unionbpms_y
    else:
        commonbpms_x = twiss_d.zero_dpp_commonbpms_x
        commonbpms_y = twiss_d.zero_dpp_commonbpms_y

    if getllm_d.nprocesses == -1:
        getllm_d.nprocesses = multiprocessing.cpu_count()
    getllm_d.parallel = (getllm_d.nprocesses > 0)
    #---- H plane
    _box_edge_()
    _info_box_("Calculating beta from phase")
    _info_box_("Version: {0:5s}".format(__version__))

    _debug_value_box_("range of BPMs", str(getllm_d.range_of_bpms))
    _debug_value_box_("cot of phase threshold", "{:g}".format(COT_THRESHOLD))

    if DEBUG:
        _info_(
            "ATTENTION:"
            " DEBUG is set to true, calculation of beta functions will be done serially"
        )
        getllm_d.parallel = False
    elif getllm_d.parallel:
        _info_value_box_("parallel", "TRUE")
        _info_value_box_("number of processes", "{0:2d}".format(getllm_d.nprocesses))
    else:
        _info_value_box_("parallel", "FALSE")

    _debug_value_box_("quad field errors", "[YES]")
    _debug_value_box_("quad long misalignments", "[YES]")
    _debug_value_box_("sext transverse misalignments", "[YES]")
    _debug_value_box_("BPM long misalignments", "[YES]")
    _debug_value_box_("dipole K1 errors", "[ NO]")
    _debug_value_box_("analytical alpha", "[ NO]")

    _box_edge_()

    starttime = time.time()

    # check whether analytical N-BPM method should be used
    # if yes, uncertainty estimates will be distributed to the elements
    # do this only once for both planes
    error_method = METH_IND
    unc_elements = None

    if getllm_d.use_only_three_bpms_for_beta_from_phase:
        error_method = METH_3BPM
    else:
        unc = Uncertainties()
        _info_("")
        _debug_("Accelerator Error Definition")
        error_defs_path = getllm_d.accelerator.get_errordefspath()
        if error_defs_path is None or not unc.open(error_defs_path):
            _error_("Error definition file couldn't be found")
            raise IOError("Error definition file '{}' could not be found"
                          .format(getllm_d.accelerator.get_errordefspath()))

        unc_elements = unc.create_errorfile(elements, elements_centre)
        error_method = METH_A_NBPM
        _info_("")

    #------------- HORIZONTAL
    if twiss_d.has_zero_dpp_x():
        beta_d.x_phase, beta_d.x_phase_f, beta_driven_x, beta_free_x = beta_from_phase_for_plane(
            free_model.loc[commonbpms_x.index], driven_model, free_bk_model, unc_elements,
            getllm_d, twiss_d, elements_centre.loc[commonbpms_x.index], phase_d.phase_advances_x,
            phase_d.phase_advances_free_x, error_method, tune_d.q1, tune_d.q1f, tune_d.q1mdl,
            tune_d.q1mdlf, files_dict, commonbpms_x, "X"
        )
    #------------- VERTICAL
    if twiss_d.has_zero_dpp_y():
        beta_d.y_phase, beta_d.y_phase_f, beta_driven_y, beta_free_y = beta_from_phase_for_plane(
            free_model.loc[commonbpms_y.index], driven_model, free_bk_model, unc_elements,
            getllm_d, twiss_d, elements_centre.loc[commonbpms_y.index], phase_d.phase_advances_y,
            phase_d.phase_advances_free_y, error_method, tune_d.q2, tune_d.q2f, tune_d.q2mdl,
            tune_d.q2mdlf, files_dict, commonbpms_y, "Y"
        )
    return beta_d, beta_driven_x, beta_free_x
# END calculate_beta_from_phase -------------------------------------------------------------------


def beta_from_phase_for_plane(free_model, driven_model, free_bk_model, unc_elements, getllm_d, twiss_d,
                              elements_centre, phase_adv, phase_adv_free, error_method, Q, Qf, Qmdl,
                              Qmdlf, files_dict, commonbpms, plane):
    """
    This function calculates and outputs the beta function measurement for the given plane.
    """
    plane_for_file = plane.lower()
    beta_d_phase_f = {}
    beta_d_phase = {}

    _info_("Calculate free beta from phase for plane " + plane + " (_free.out)", ">")
    debugfile = None
    if DEBUG:
        debugfile = DBG.create_debugfile(
            files_dict['getbeta{}_free.out'.format(plane_for_file)].s_output_path +
            "/getbeta{}_free.bdebug".format(plane_for_file)
        )

    dataf, rms_bb, bpmsf, error_method_x = beta_from_phase(
        free_model, unc_elements, elements_centre, twiss_d.zero_dpp_x, commonbpms,
        phase_adv_free, plane, getllm_d, debugfile, error_method, Qf, Qmdlf%1.0
    )

    if DEBUG:
        DBG.close_file()
    beta_d_phase_f['DPP'] = 0

    tfs_file = files_dict['getbeta{}_free.out'.format(plane_for_file)]
    tfs_file.add_header("Q1", getllm_d.accelerator.nat_tune_x)
    tfs_file.add_header("Q2", getllm_d.accelerator.nat_tune_y)
    beta_data_frame_free =_write_getbeta_out(
        getllm_d.number_of_bpms, getllm_d.range_of_bpms, beta_d_phase_f, dataf, free_model,
        error_method_x, commonbpms, tfs_file, plane, getllm_d.union
    )
    _write_getbeta_out
    beta_d_phase = deepcopy(beta_d_phase_f)

    if getllm_d.accelerator.excitation is not AccExcitationMode.FREE:
        driven_model = driven_model.loc[commonbpms.index]
        _info_("Calculate beta from phase for plane " + plane, ">")
        if DEBUG:
            debugfile = DBG.create_debugfile(
                files_dict['getbeta{}.out'.format(plane_for_file)].s_output_path +
                "/getbeta{}.bdebug".format(plane_for_file)
            )

        data, rms_bb, bpms, error_method_x = beta_from_phase(
            driven_model, unc_elements, elements_centre, twiss_d.zero_dpp_x, commonbpms,
            phase_adv, plane, getllm_d, debugfile, error_method, Q, Qmdl%1.0
        )

        if DEBUG:
            DBG.close_file()
        beta_d_phase['DPP'] = 0
        tfs_file = files_dict['getbeta{}.out'.format(plane_for_file)]

        tfs_file.add_header("Q1", getllm_d.accelerator.nat_tune_x)
        tfs_file.add_header("Q2", getllm_d.accelerator.nat_tune_y)

        beta_data_frame = _write_getbeta_out(
            getllm_d.number_of_bpms, getllm_d.range_of_bpms, beta_d_phase, data, driven_model,
            error_method_x, commonbpms, tfs_file, plane, getllm_d.union
        )

        _debug_("Skip free2 calculation")
    return beta_d_phase, beta_d_phase_f, beta_data_frame, beta_data_frame_free


# END calculate_beta_from_amplitude ----------------------------------------------------------------


def beta_from_phase(madTwiss, madElements, madElementsCentre, ListOfFiles, commonbpms, phase, plane,
                    getllm_d, debugfile, errors_method, tune, mdltune):
    '''
    Calculate the beta function from phase advances
    If range of BPMs is sufficiently large use averaging with weighted mean. The weights are
    determinde using either the output of Monte Carlo simulations or using analytical formulas
    derived from exacter formulas to calculate the beta function.

    TODO: rewrite docstring.
    '''
    rmsbb = 0.0
    #---- Error definitions given and we decided to use => use analytical formulas to calculate the
    # systematic errors
    if errors_method == METH_A_NBPM:
        errors_method, data = scan_all_BPMs_withsystematicerrors(
            madTwiss, madElements, phase, plane, getllm_d, commonbpms, debugfile, errors_method,
            tune, mdltune
        )
        return data, rmsbb, commonbpms, errors_method
    #---- use the simulations
    else:
        rmsbb, errors_method, data = scan_all_BPMs_sim_3bpm(
            madTwiss, phase, plane, getllm_d, commonbpms, debugfile, errors_method, tune, mdltune
        )

    return data, rmsbb, commonbpms, errors_method





#---------------------------------------------------------------------------------------------------
#----------------- calculate beta and alpha using the old 3 BPM method -----------------------------
#---------------------------------------------------------------------------------------------------
def scan_all_BPMs_sim_3bpm(madTwiss, phase, plane, getllm_d, commonbpms, debugfile, errors_method, tune, mdltune):
    '''
    Calculates beta from phase using the old 3-BPM method
    Fast 'vectorized' pandas / numpy code

    ``phase["MEAS"]``, ``phase["MODEL"]``, ``phase["ERRMEAS"]`` (from ``get_phases``) are of the form:

    +----------+----------+----------+----------+----------+
    |          |   BPM1   |   BPM2   |   BPM3   |   BPM4   |
    +----------+----------+----------+----------+----------+
    |   BPM1   |    0     |  phi_21  |  phi_31  |  phi_41  |
    +----------+----------+----------+----------+----------+
    |   BPM2   |  phi_12  |     0    |  phi_32  |  phi_42  |
    +----------+----------+----------+----------+----------+
    |   BPM3   |  phi_13  |  phi_23  |    0     |  phi_43  |
    +----------+----------+----------+----------+----------+

    aa ``tilt_slice_matrix(matrix, shift, slice, tune)`` brings it into the form:

    +-----------+--------+--------+--------+--------+
    |           |  BPM1  |  BPM2  |  BPM3  |  BPM4  |
    +-----------+--------+--------+--------+--------+
    | BPM_(i-1) | phi_1n | phi_21 | phi_32 | phi_43 |
    +-----------+--------+--------+--------+--------+
    | BPM_i     |    0   |    0   |    0   |    0   |
    +-----------+--------+--------+--------+--------+
    | BPM_(i+1) | phi_12 | phi_23 | phi_34 | phi_45 |
    +-----------+--------+--------+--------+--------+

    ``cot_phase_*_shift1``:

    +-----------------------------+-----------------------------+-----------------------------+
    | cot(phi_1n) - cot(phi_1n-1) |  cot(phi_21) - cot(phi_2n)  |   cot(phi_32) - cot(phi_31) |
    +-----------------------------+-----------------------------+-----------------------------+
    |         NaN                 |         NaN                 |         NaN                 |
    +-----------------------------+-----------------------------+-----------------------------+
    |         NaN                 |         NaN                 |         NaN                 |
    +-----------------------------+-----------------------------+-----------------------------+
    |  cot(phi_13) - cot(phi_12)  |  cot(phi_24) - cot(phi_23)  |   cot(phi_35) - cot(phi_34) |
    +-----------------------------+-----------------------------+-----------------------------+

    for the combination xxxABBx: first row
    for the combinstion xBBAxxx: fourth row and
    for the combination xxBABxx: second row of ``cot_phase_*_shift2``
    '''
    number_commonbpms = commonbpms.shape[0]
    plane_bet = "BET" + plane
    plane_alf = "ALF" + plane

    if errors_method == METH_3BPM:
        madTwiss_intersected = madTwiss.loc[commonbpms.index]
        starttime = time.time()

        # ------ setup the used variables ----------------------------------------------------------
        # tilt phase advances in order to have the phase advances in a neighbourhood
        tilted_meas = tilt_slice_matrix(phase["MEAS"].as_matrix(), 2, 5, tune) * TWOPI
        tilted_model = tilt_slice_matrix(phase["MODEL"].as_matrix(), 2, 5, mdltune) * TWOPI
        tilted_errmeas = tilt_slice_matrix(phase["ERRMEAS"].as_matrix(), 2, 5, mdltune) * TWOPI

        betmdl = madTwiss_intersected.loc[:][plane_bet].as_matrix()
        alfmdl = madTwiss_intersected.loc[:][plane_alf].as_matrix()

        # ------ main part, calculate the beta and alpha function ----------------------------------

        # calculate cotangens of all the phase advances in the neighbourhood
        with np.errstate(divide='ignore'):
            cot_phase_meas = 1.0 / tan(tilted_meas)
            cot_phase_model = 1.0 / tan(tilted_model)

        # calculate enumerators and denominators for far more cases than needed
        # shift1 are the cases BBA, ABB, AxBB, AxxBB etc. (the used BPMs are adjacent)
        # shift2 are the cases where the used BPMs are separated by one. only BAB is used for  3-BPM
        cot_phase_meas_shift1 = cot_phase_meas - np.roll(cot_phase_meas, -1, axis=0)
        cot_phase_model_shift1 = cot_phase_model - np.roll(cot_phase_model, -1, axis=0) + 1.0e-16
        cot_phase_meas_shift2 = cot_phase_meas - np.roll(cot_phase_meas, -2, axis=0)
        cot_phase_model_shift2 = cot_phase_model - np.roll(cot_phase_model, -2, axis=0)+ 1.0e-16

        # calculate the sum of the fractions
        bet_frac = (cot_phase_meas_shift1[0]/cot_phase_model_shift1[0] +
                    cot_phase_meas_shift1[3]/cot_phase_model_shift1[3] +
                    cot_phase_meas_shift2[1]/cot_phase_model_shift2[1]) / 3.0

        # multiply the fractions by betmdl and calculate the arithmetic mean
        beti = bet_frac * betmdl

        # alpha
        alfi = (bet_frac * (cot_phase_model[1] + cot_phase_model[3] + 2.0 * alfmdl)
                - (cot_phase_meas[1] + cot_phase_meas[3])) / 2.0

        # ------ error propagation -----------------------------------------------------------------

        # error = sqrt( errphi_ij^2 * (d beta / dphi_ij)^2 )
        # calculate sin(phimdl_ij)
        sin_model = sin(tilted_model)
        # calculate errphi_ij^2 / sin^2 phimdl_ij * beta
        with np.errstate(divide='ignore', invalid='ignore'):
            sin_squared_model = tilted_errmeas / np.multiply(sin_model, sin_model) * betmdl
        # square it again beacause it's used in a vector length
        sin_squared_model = np.multiply(sin_squared_model, sin_squared_model)

        sin_squ_model_shift1 = sin_squared_model + \
                np.roll(sin_squared_model, -1, axis=0) / \
                np.multiply(cot_phase_model_shift1, cot_phase_model_shift1)
        sin_squ_model_shift2 = sin_squared_model + \
                np.roll(sin_squared_model, -2, axis=0) / \
                np.multiply(cot_phase_model_shift2, cot_phase_model_shift2)
        beterr = np.sqrt(sin_squ_model_shift1[0] + sin_squ_model_shift1[3] +
                         sin_squ_model_shift2[1]) \
                / 3.0

        betstd = np.zeros(number_commonbpms)
        alfstd = np.zeros(number_commonbpms)
        alferr = np.zeros(number_commonbpms)

        # ------ print error method and return the data rows for getbetax/y.out --------------------

        _info_("Errors from " + ID_TO_METHOD[errors_method])

        bb = (bet_frac - 1.0) * 100.0

        return sqrt(np.mean(np.multiply(bb,bb))), errors_method, \
                np.transpose([
                    commonbpms.index, madTwiss_intersected.loc[:]["S"],
                    beti, betstd, betstd, beterr,
                    alfi, alfstd, alfstd, alfstd,
                    alfi,
                    betmdl,
                    bb,
                    alfi])
    raise GetLLMError("Monte Carlo N-BPM is not implemented.")

#---------------------------------------------------------------------------------------------------
#--------- using analytical formula ----------------------------------------------------------------
#---------------------------------------------------------------------------------------------------



def scan_all_BPMs_withsystematicerrors(madTwiss, madElements,
                                       phase, plane, getllm_d, commonbpms, debugfile, errors_method,
                                       tune, mdltune):
    '''
    If errorfile is given (!= "0") this function calculates the beta function for each BPM using the analytic expression
    for the estimation of the error matrix.
    '''

    _info_("Errors from " + ID_TO_METHOD[errors_method])
    _plane_char = str.upper(plane)
    LOGGER.debug("starting scan_all_BPMs_withsystematicerrors")
    # --------------- alphas from 3BPM -------------------------------------------------
    _, _, data3bpm = scan_all_BPMs_sim_3bpm(madTwiss,
                                            phase, plane, getllm_d, commonbpms, debugfile, METH_3BPM,
                                            tune, mdltune)

    # ---------- setup -----------------------------------------------------------------------------
    # setup combinations
    width = getllm_d.range_of_bpms / 2
    left_bpm = range(-width, 0)
    right_bpm = range(0 + 1, width + 1)
    BBA_combo = [[x, y] for x in left_bpm for y in left_bpm if x < y]
    ABB_combo = [[x, y] for x in right_bpm for y in right_bpm if x < y]
    BAB_combo = [[x, y] for x in left_bpm for y in right_bpm]
    print len(ABB_combo) , len(BAB_combo) , len(BBA_combo)

    # get the model values only for used elements, so that commonbps[i] = masTwiss[i]
    madTwiss_intersected = madTwiss.loc[commonbpms.index]
    mu = "MU" + plane
    mu_elements = madElements.loc[:][mu].values

    # for fast access
    phases_meas = phase["MEAS"] * TWOPI
    phases_model = phase["MODEL"] * TWOPI
    phases_err = phase["ERRMEAS"] * TWOPI

    # setup the results matrix
    result = np.array(np.empty(madTwiss_intersected.shape[0]),
                      dtype = [("NAME", "S24"), ("S", "f8"),
                               ("BET" + _plane_char, "f8"),
                               ("STATBET" + _plane_char, "f8"),
                               ("SYSBET" + _plane_char, "f8"),
                               ("ERRBET" + _plane_char, "f8"),
                               ("ALF" + _plane_char, "f8"),
                               ("STATALF" + _plane_char, "f8"),
                               ("SYSALF" + _plane_char, "f8"),
                               ("ERRALF" + _plane_char, "f8"),
                               ("CORR", "f8"),
                               ("BET" + _plane_char + "MDL", "f8"),
                               ("BBEAT", "f8"), ("NCOMB", "i4")])

    # ----------
    # define functions in a function -- python witchcraft, burn it!!!!! 
    def collect(row):
        result[row[0]] = row[1:]

    def collectblock(block):
        for row in block:
            collect(row)
     # ---------- calculate the betas --------------------------------------------------------------

    st = time.time()
    if getllm_d.parallel:

        # setup thread pool and data chunks
        chunksize = int(len(commonbpms) / getllm_d.nprocesses) + 1
        pool = multiprocessing.Pool()
        n = int(len(commonbpms) / chunksize)

        for i in range(n):
            pool.apply_async(scan_several_BPMs_withsystematicerrors,
                             (madTwiss_intersected, madElements,
                              phases_meas, phases_err,
                              plane, getllm_d.range_of_bpms, commonbpms, debugfile,
                              i * chunksize, (i + 1) * chunksize, BBA_combo, ABB_combo, BAB_combo,
                              tune, mdltune),
                             callback=collectblock)

        # calculate the last, incomplete chunk
        pool.apply_async(scan_several_BPMs_withsystematicerrors,
                         (madTwiss_intersected, madElements,
                          phases_meas, phases_err,
                          plane, getllm_d.range_of_bpms, commonbpms, debugfile,
                          n * chunksize, len(commonbpms), BBA_combo, ABB_combo, BAB_combo,
                          tune, mdltune),
                         callback=collectblock)

        # wait for all the threads to finish and join the results
        pool.close()
        pool.join()
    else:  # not parallel
        for i in range(0, len(commonbpms)):
            row = scan_one_BPM_withsystematicerrors(madTwiss_intersected, madElements,
                                                    phases_meas, phases_err,
                                                    plane, getllm_d.range_of_bpms, commonbpms,
                                                    debugfile, i,
                                                    BBA_combo, ABB_combo, BAB_combo,
                                                    tune, mdltune)
            collect(row)
    et = time.time()

    _debug_("time elapsed = {0:3.3f}".format(et - st))

    result["ALF" + plane] = data3bpm[:, 6]
    result["STATALF" + plane] = data3bpm[:, 7]
    result["SYSALF" + plane] = data3bpm[:, 8]
    result["ERRALF" + plane] = data3bpm[:, 9]
    #result["BETERR"] *= np.sqrt(commonbpms.loc[:, "NFILES"])
    return errors_method, result


def scan_several_BPMs_withsystematicerrors(madTwiss, madElements,
                                           cot_meas, phases_err,
                                           plane, range_of_bpms, commonbpms, debugfile,
                                           begin, end, BBA_combo, ABB_combo, BAB_combo,
                                           tune, mdltune):
    block = []
    for i in range(begin, end):
        block.append(scan_one_BPM_withsystematicerrors(madTwiss, madElements,
                                                       cot_meas, phases_err,
                                                       plane, range_of_bpms, commonbpms,
                                                       debugfile, i,
                                                       BBA_combo, ABB_combo, BAB_combo,
                                                       tune, mdltune))
    return block

    #TODO: rewrite the docstring.
def scan_one_BPM_withsystematicerrors(madTwiss, madElements,
                                      phases_meas, phases_err,
                                      plane, range_of_bpms, commonbpms, debugfile,
                                      Index, BBA_combo, ABB_combo, BAB_combo,
                                      tune, mdltune):
    '''
    Scans the range of BPMs in order to get the final value for one BPM in the lattice

    :Parameters:
        'madTwiss':tfs_pandas
            The model twiss table, contains all the BPMs. Has to be already intersected with the common BPMs:

           +-------+----+-------+-----+-----+-------+
           |       | S  | BETX  | MUX | ... | BETY  |
           +-------+----+-------+-----+-----+-------+
           |  BPM1 | s1 | beta1 | mu1 | ... | bety1 |
           +-------+----+-------+-----+-----+-------+
           |  BPM2 | s2 | beta2 | mu2 | ... | bety2 |
           +-------+----+-------+-----+-----+-------+
           |  ...  |    |       |     |     |       |
           +-------+----+-------+-----+-----+-------+
           |  BPMn | sn | betan | mun | ... | betyn |
           +-------+----+-------+-----+-----+-------+

        'madElements':tfs_pandas
            Twiss table of all elements with known uncertainties.

           +------+--------+-----------+---------+-----+--------+---------+--------+
           |      | S      | BETX      | MUX     | ... | dK1    | dS      | BPMdS  |
           +------+--------+-----------+---------+-----+--------+---------+--------+
           | BPM1 | s1     | beta1     | mu1     | ... | 0      | 0       | 1e-3   |
           +------+--------+-----------+---------+-----+--------+---------+--------+
           | MQ1  | s(El1) | beta(El1) | mu(El1) | ... | 1e-4   | 0       | 0      |
           +------+--------+-----------+---------+-----+--------+---------+--------+
           | MQ2  | s(El2) | beta(El2) | mu(El2) | ... | 2e-4   | 0       | 0      |
           +------+--------+-----------+---------+-----+--------+---------+--------+
           | MS1  | s(El3) | beta(El3) | mu(El3) | ... | 0      | 1.0e-3  | 0      |
           +------+--------+-----------+---------+-----+--------+---------+--------+
           | BPM2 | s2     | beta2     | mu2     | ... | 0      | 0       | 1e-3   |
           +------+--------+-----------+---------+-----+--------+---------+--------+
           | ...  | ...    | ...       | ...     | ... | ...    | ...     | ...    |
           +------+--------+-----------+---------+-----+--------+---------+--------+
           | BPMn | sn     | betan     | mun     | ... | 0      | 0       | 1e-3   |
           +------+--------+-----------+---------+-----+--------+---------+--------+
             
             for later distinction we denote the row index of madElements by <l>:
                 s<1> := s1
                 s<2> := s(El1)
                 s<3> := s(El2)
                 etc.
             
        'phases_meas/phases_model':numpy.ndarray
            matrix of the cotanges of the meas/model phase advances.
            
                  | BPM1   | BPM2   | ... | BPMn 
            ------+--------+--------+-----+-----
             BPM1 | 0      | phi_21 | ... | phi_n1 
             BPM2 | phi_12 | 0      | ... | phi_n2
             ...  | ...    | ...    | ... | ...   
             BPMn | phi_1n | phi_2n | ... | 0 

             index and columns: madTwiss.index

             cotangens of shifted and sliced:

                      | BPM1 | BPM2 | ...  | BPMn 
            ----------|------|------|------|-----
             BPM(i-2) | *    | *    | ...  | * 
             BPM(i-1) | *    | *    | ...  | * 
             BPMi     | 0    | 0    | 0..0 | 0   
             BPM(i+1) | *    | *    | ...  | * 
             BPM(i+2) | *    | *    | ...  | * 

             where * = cot(phi_j - phi_i) =: cot(phi_ij)


        'phases_elements':numpy.ndarray

                 | BPM1 | MQ1 | MQ2 | MS1 | BPM2 | ... | BPMn
            -----|------|-----|-----|-----|------|-----|------
            BPM1 | 0    | *   | *   | *   | *    | ... | *
            BPM2 | *    | *   | *   | *   | 0    | ... | *
            BPM3 | *    | *   | *   | *   | *    | ... | *
            ...  | ...  | ... | ... | ... | ...  | ... | ...
            BPMn | *    | *   | *   | *   | *    | ... | 0

            where * = phi_j - phi<i>

            columns: madElements.index
            rows: madTwiss.index

    IMPORTANT NOTE: from the above only madTwiss and madElements are pandas.DataFrames, cot_meas and sin_squared_elements
                    are numpy arrays and thus are not equipped with an index or column headers.

    The heavy fancy indexing part is explained in detail:
        In the following the probed BPM has the name probed_bpm and the index i. The range of BPMs has the length J and
        m = floor(J/2).

        The range of BPMs is then [BPM(i-m), ..., BPM(i-1), BPMi, BPM(i+1), ... BPM(i+m)]
        The combinations are split into the three cases BBA, BAB, ABB
        BBA_combo = [(-m, -m+1), ... (-2, -1)]
        BAB_combo = [(-m, 1), ... (-m, m), (-m+1, 1), ... (-m+1, m), ... (-1, m)]
        ABB_combo = [(1,2), ... (m-1, m)]

        for each (j,k) in combos: calculate beta and row of the Jacobian T:

            beta_i(combo) = (cot(phi_ij) - cot(phi_ik)) / (cot(phimdl_ij) - cot(phimdl_ik)) * betmdl_i for (j,k) in combo

        So, before we start the loop, let's slice out the interval of all BPMs and all elements that are reached by the
        combinations (outer interval) at this time we can apply the tune jump, wrap the interval and calculate the 
        trigonometric functions of the phase advances

         - for this we need cot(phi_(i)(i-m) ... cot(phi_(i)(i+m)) and idem for the model phases 

            K-part of the Jacobian
            T_k(combo) = betmdl_i * betmdl<l> / (cot(phimdl_ij) - cot(phimdl_ik)) *
                            (
                            sin^2(phimdl_j - phimdl<l>) / sin^2(phimdl_j - phimdl_i) * A(i,j) - 
                            sin^2(phimdl_k - phimdl<l>) / sin^2(phimdl_k - phimdl_i) * A(i,k)
                            )
            where A(i,j) = 1 if i < j, else -1 and it is 0 if <l> is not between BPMi and BPMj
            => BBA_combo: A(i,j) = -1, A(i,k) = -1
               BAB_combo: A(i,j) = -1, A(i,k) = 1
               ABB_combo: A(i,j) = A(i,k) = 1
         - for this we need sin^2(phimdl_(i-m) - phimdl_(i-m+<1>)), sin^2(phimdl_(i-m) - phimdl_(i-m+<2>)), ...
                              sin^2(phimdl_(i+m) - phimdl_(i+m-<2>)), sin^2(phimdl_(i+m) - phimdl_(i+m-<1>))
            which is again the range of BPMs but with all other Elements lying between them.

        Take the left-most combination, that is (i-m, i-m+1). By construction of the combo sets this is the first
        combination in BBA_combo. Analogously the right-most combination is the last element of ABB_combo.

        IDEA: Use the index of madTwiss and madElements to get the location of the start and end elements and then slice 
        intelligently. 

        indx_first = indx_(i-m) = i-m
        indx_last = indx(i+m) = i+m
        name_first = madTwiss.index[indx_first], same for last
        indx<first> = madElements.index.get_loc(name_first), same for last
        
        if indx_(i-m) < 0: 
            have to wrap around and add the tune
            outer_interval_meas = [phases_meas[index%length] ...] + tune concat [phases_meas[0] ...]
                same for outer_interval_model
            outer_interval_elements = [phases_elements[indx<first>] ... phases_elements[length]] + tune
                                        concat  [phases_elements[0] ... phases_elements[indx<last>]]
        else if indx_(i+m) > length: analogously
        else: simple
    '''
    probed_bpm_name = madTwiss.index[Index]
    s = madTwiss.at[probed_bpm_name, "S"]


    betmdl1 = madTwiss.at[probed_bpm_name, "BET" + plane]
    alfmdl1 = madTwiss.at[probed_bpm_name, "ALF" + plane]
    mu_column = "MU" + plane
    bet_column = "BET" + plane

    beti        = DEFAULT_WRONG_BETA    #@IgnorePep8
    betstat     = .0                    #@IgnorePep8
    betsys      = .0                    #@IgnorePep8
    beterr      = DEFAULT_WRONG_BETA    #@IgnorePep8
    alfi        = DEFAULT_WRONG_BETA    #@IgnorePep8
    alfstat     = .0                    #@IgnorePep8
    alfsys      = .0                    #@IgnorePep8
    alferr      = DEFAULT_WRONG_BETA    #@IgnorePep8
    corr        = .0                    #@IgnorePep8
    used_bpms   = -2                     #@IgnorePep8

    m = range_of_bpms / 2
    indx_first = Index - m
    indx_last = Index + m
    name_first = madTwiss.index[indx_first]
    name_last = madTwiss.index[indx_last% len(madTwiss.index)]
    probed_bpm_name = madTwiss.index[Index]
    len_bpms_total = phases_meas.shape[0]

    indx_el_first = madElements.index.get_loc(name_first)
    indx_el_last= madElements.index.get_loc(name_last )

    if indx_first < 0:
        outerMeasPhaseAdv = pd.concat((
                phases_meas.iloc[Index, indx_first % len_bpms_total:] - tune * TWOPI,
                phases_meas.iloc[Index, :indx_last+1]))
        outerMeasErr = pd.concat((
                phases_err.iloc[Index, indx_first % len_bpms_total:],
                phases_err.iloc[Index, :indx_last+1]))
        outerMdlPh = np.concatenate((
                madTwiss.iloc[indx_first % len_bpms_total:][mu_column] - mdltune,
                madTwiss.iloc[:indx_last+1][mu_column])) * TWOPI
        outerElmts = pd.concat((
                madElements.iloc[indx_el_first:],
                madElements.iloc[:indx_el_last + 1]))
        outerElmtsPh = np.concatenate((
                madElements.iloc[indx_el_first:][mu_column] - mdltune,
                madElements.iloc[:indx_el_last + 1][mu_column])) * TWOPI

    elif indx_last >= len_bpms_total:
        outerMeasPhaseAdv = pd.concat((
                phases_meas.iloc[Index, indx_first:],
                phases_meas.iloc[Index, :(indx_last + 1) % len_bpms_total] + tune * TWOPI))
        outerMeasErr = pd.concat((
                phases_err.iloc[Index, indx_first:],
                phases_err.iloc[Index, :(indx_last + 1) % len_bpms_total]))
        outerMdlPh = np.concatenate((
                madTwiss.iloc[indx_first:][mu_column],
                madTwiss.iloc[:(indx_last + 1) % len_bpms_total][mu_column]  + mdltune)) * TWOPI
        outerElmts = pd.concat((
                madElements.iloc[indx_el_first:],
                madElements.iloc[:indx_el_last + 1]))
        outerElmtsPh = np.concatenate((
                madElements.iloc[indx_el_first:][mu_column],
                madElements.iloc[:indx_el_last + 1][mu_column] + mdltune)) * TWOPI

    else:
        outerMeasPhaseAdv = phases_meas.iloc[Index, indx_first : indx_last + 1]
        outerMeasErr = phases_err.iloc[Index, indx_first : indx_last + 1]
        outerMdlPh = madTwiss.iloc[indx_first:indx_last + 1][mu_column].as_matrix() * TWOPI
        outerElmts = madElements.iloc[indx_el_first:indx_el_last + 1]
        outerElmtsPh = madElements.iloc[indx_el_first:indx_el_last + 1][mu_column] * TWOPI

    outerMeasErr = np.multiply(outerMeasErr, outerMeasErr)

    outerElPhAdv = (outerElmtsPh[:, np.newaxis] - outerMdlPh[np.newaxis, :])
    outerElK2 = outerElmts.loc[:, "K2L"].as_matrix()
    indx_el_probed = outerElmts.index.get_loc(probed_bpm_name)
    outerElmtsBet = outerElmts.loc[:][bet_column].as_matrix()

    with np.errstate(divide='ignore'):
        cot_meas = 1.0 / tan(outerMeasPhaseAdv.as_matrix())
        cot_model = 1.0 / tan((outerMdlPh - outerMdlPh[m]))
    outerElPhAdv = sin(outerElPhAdv)
    sin_squared_elements = np.multiply(outerElPhAdv, outerElPhAdv)

    betas = np.empty(len(BBA_combo) + len(BAB_combo) + len(ABB_combo))
    alfas = np.empty(len(BBA_combo) + len(BAB_combo) + len(ABB_combo))
    beta_mask = np.empty(len(BBA_combo) + len(BAB_combo) + len(ABB_combo), dtype=bool)

    diag = np.concatenate((outerMeasErr.as_matrix(), outerElmts.loc[:]["dK1"],
                           outerElmts.loc[:]["dX"], outerElmts.loc[:]["KdS"],
                           outerElmts.loc[:]["mKdS"]))
    mask = diag != 0

    T_Beta = np.zeros((len(betas),
                       len(diag) ))
    T_Alfa = np.zeros((len(betas),
                       len(diag) ))

    M = np.diag(diag[mask])
    line_length = len(diag)

    for i, combo in enumerate(BBA_combo):
        ix = combo[0] + m
        iy = combo[1] + m
        beta, alfa, betaline, alfaline = get_combo(
            ix, iy, sin_squared_elements, outerElmts, outerElmtsBet, outerElK2, cot_model, cot_meas,
            outerMeasPhaseAdv, combo, indx_el_probed, line_length, betmdl1, alfmdl1,
            range_of_bpms, m,
            1.0, -1.0, 1.0, -1.0)
        if beta > 0:
            T_Beta[i] = betaline
            T_Alfa[i] = alfaline
            betas[i] = beta
            alfas[i] = alfa
            beta_mask[i] = True
        else:
            beta_mask[i] = False

    for j, combo in enumerate(BAB_combo):
        ix = combo[0] + m
        iy = combo[1] + m
        i = j + len(BBA_combo)


        beta, alfa, betaline, alfaline = get_combo(
            ix, iy, sin_squared_elements, outerElmts, outerElmtsBet, outerElK2, cot_model, cot_meas,
            outerMeasPhaseAdv, combo, indx_el_probed, line_length, betmdl1, alfmdl1,
            range_of_bpms, m,
            1.0, 1.0, 1.0, 1.0)
        if beta > 0:
            T_Beta[i] = betaline
            T_Alfa[i] = alfaline
            betas[i] = beta
            alfas[i] = alfa
            beta_mask[i] = True
        else:
            beta_mask[i] = False

    for j, combo in enumerate(ABB_combo):
        ix = combo[0] + m
        iy = combo[1] + m

        i = j + len(BBA_combo) + len(BAB_combo)

        beta, alfa, betaline, alfaline = get_combo(
            ix, iy, sin_squared_elements, outerElmts, outerElmtsBet, outerElK2, cot_model, cot_meas,
            outerMeasPhaseAdv, combo, indx_el_probed, line_length, betmdl1, alfmdl1,
            range_of_bpms, m,
            -1.0, +1.0, -1.0, 1.0)

        if beta > 0:
            T_Beta[i] = betaline
            T_Alfa[i] = alfaline
            betas[i] = beta
            alfas[i] = alfa
            beta_mask[i] = True
        else:
            beta_mask[i] = False
    T_Beta = T_Beta[:, mask]
    T_Beta = T_Beta[beta_mask]
    betas = betas[beta_mask]
    V_Beta = np.dot(T_Beta, np.dot(M,np.transpose(T_Beta)))
    try:
        V_Beta_inv = np.linalg.pinv(V_Beta, rcond=RCOND)
        w = np.sum(V_Beta_inv, axis=1)
#        print w
#        raw_input()
        VBeta_inv_sum = np.sum(w)
        if VBeta_inv_sum == 0:
            raise ValueError
        beterr = math.sqrt(float(np.dot(np.transpose(w), np.dot(V_Beta, w)) / VBeta_inv_sum ** 2))
        beti = float(np.dot(np.transpose(w), betas) / VBeta_inv_sum)
        used_bpms = len(betas)
    except:
        _debug_("ValueError at {}".format(probed_bpm_name))
        _debug_("betas:\n" + str(betas))

        return (
            Index, probed_bpm_name, s,
            beti, betstat, betsys, beterr,
            alfi, alfstat, alfsys, alferr,
            .0, betmdl1, (beti - betmdl1) / betmdl1 * 100.0,
            -2
        )
    #------------------------------------------------------------------------------------------------------------------
    # writing debug output
    #------------------------------------------------------------------------------------------------------------------
    if DEBUG:
        DBG.start_write_bpm(probed_bpm_name, s, beti, alfi, 0)
        DBG.write_matrix(T_Beta, "T_Beta")
        DBG.start_write_combinations(len(betas))
        combs = np.r_[BBA_combo, BAB_combo, ABB_combo] # Stackexchange
        combs = combs[beta_mask]
        for n, beta_of_comb in enumerate(betas):
            DBG.write_bpm_combination(combs[n][0], combs[n][1], beta_of_comb, w[n] / VBeta_inv_sum)
        DBG.write_double("PHI{}MDL".format(plane), outerMdlPh[m])

        DBG.write_end()

    return (
        Index, probed_bpm_name, s,
        beti, betstat, betsys, beterr,
        alfi, alfstat, alfsys, alferr,
        .0, betmdl1, (beti - betmdl1) / betmdl1 * 100.0,
        len(betas)
    )

def get_combo(ix, iy, sin_squared_elements, outerElmts, outerElmtsBet, outerElK2, cot_model,
              cot_meas, outerMeasPhaseAdv,
              combo, indx_el_probed, line_length, betmdl1, alfmdl1, range_of_bpms, m,
              fac1, fac2, sfac1, sfac2):
    betaline = np.zeros((line_length))
    alfaline = np.zeros((line_length))

    # remove bad combination
    if (abs(cot_model[ix]) > COT_THRESHOLD or
        abs(cot_model[iy]) > COT_THRESHOLD or
        abs(cot_meas[ix]) > COT_THRESHOLD or
        abs(cot_meas[iy]) > COT_THRESHOLD
        or abs(cot_model[ix] - cot_model[iy]) < ZERO_THRESHOLD):
        return -1.0, -1.0, None, None

    # calculate beta
    denom = (cot_model[ix] - cot_model[iy]) / betmdl1
    denomalf = denom * betmdl1 + 2 * alfmdl1
    beta_i = (cot_meas[ix] - cot_meas[iy]) / denom
    alfa_i = 0.5 * (denomalf * beta_i / betmdl1
                    - (cot_meas[ix] + cot_meas[iy]))

    # slice
    xloc = outerElmts.index.get_loc(outerMeasPhaseAdv.index[ix])
    yloc = outerElmts.index.get_loc(outerMeasPhaseAdv.index[iy])

    # get betas and sin for the elements in the slice
    elementPh_XA = sin_squared_elements[xloc:indx_el_probed, ix]
    elementPh_YA = sin_squared_elements[yloc:indx_el_probed, iy]
    elementBet_XA = outerElmtsBet[xloc:indx_el_probed]
    elementBet_YA = outerElmtsBet[yloc:indx_el_probed]
    elementK2_XA = outerElK2[xloc:indx_el_probed]
    elementK2_YA = outerElK2[yloc:indx_el_probed]
    denom_sinx = sin_squared_elements[xloc, m]
    denom_siny = sin_squared_elements[yloc, m]

    # apply phase uncertainty
    betaline[ix] = -1.0 / (denom_sinx * denom)
    betaline[iy] = 1.0 / (denom_siny * denom)

    alfaline[ix] = -1.0 / (denom_sinx * denom * betmdl1) * denomalf + 1.0 / denom_sinx
    alfaline[iy] = 1.0 / (denom_siny * denom * betmdl1) * denomalf + 1.0 / denom_siny

    # apply quadrupolar field uncertainty (quadrupole longitudinal misalignment already included)

    bet_sin_ix = elementPh_XA * elementBet_XA / (denom_sinx * denom)
    bet_sin_iy = elementPh_YA * elementBet_YA / (denom_siny * denom)

    betaline[xloc+range_of_bpms:indx_el_probed+range_of_bpms] += fac1 * bet_sin_ix
    betaline[yloc+range_of_bpms:indx_el_probed+range_of_bpms] += fac2 * bet_sin_iy

    alfaline[xloc+range_of_bpms:indx_el_probed+range_of_bpms] += fac1 * (
        .5 * (bet_sin_ix * denomalf + bet_sin_ix / betmdl1 * (cot_meas[ix] - cot_meas[iy])))

    alfaline[yloc+range_of_bpms:indx_el_probed+range_of_bpms] += fac2 * (
        .5 * (bet_sin_iy * denomalf + bet_sin_iy / betmdl1 * (cot_meas[ix] - cot_meas[iy])))

    y_offset = range_of_bpms + len(outerElmts)

    # apply sextupole transverse misalignment
    betaline[xloc + y_offset : indx_el_probed + y_offset] += fac1 * elementK2_XA * bet_sin_ix
    betaline[yloc + y_offset : indx_el_probed + y_offset] += fac2 * elementK2_YA * bet_sin_iy

    alfaline[xloc + y_offset : indx_el_probed + y_offset] += sfac1 * elementK2_XA * bet_sin_ix
    alfaline[yloc + y_offset : indx_el_probed + y_offset] += sfac2 * elementK2_YA * bet_sin_iy

    y_offset += len(outerElmts)

    # apply quadrupole longitudinal misalignments
    betaline[xloc + y_offset : indx_el_probed + y_offset] += fac1 * bet_sin_ix
    betaline[yloc + y_offset : indx_el_probed + y_offset] += fac2 * bet_sin_iy

    alfaline[xloc + y_offset : indx_el_probed + y_offset] +=  fac1 * (
        .5 * elementK2_XA * (bet_sin_ix * denomalf + bet_sin_ix / betmdl1 * (cot_meas[ix] -
                                                                             cot_meas[iy])))
    alfaline[yloc + y_offset : indx_el_probed + y_offset] +=  fac2 * (
        .5 * elementK2_YA * (bet_sin_iy * denomalf + bet_sin_iy / betmdl1 * (cot_meas[ix] -
                                                                             cot_meas[iy])))

    y_offset += len(outerElmts)

    betaline[xloc + y_offset : indx_el_probed + y_offset] -= fac1 * bet_sin_ix
    betaline[yloc + y_offset : indx_el_probed + y_offset] -= fac2 * bet_sin_iy

    alfaline[xloc + y_offset : indx_el_probed + y_offset] -=  fac1 * (
        .5 * (bet_sin_ix * denomalf + bet_sin_ix / betmdl1 * (cot_meas[ix] - cot_meas[iy])))
    alfaline[yloc + y_offset : indx_el_probed + y_offset] -= fac2 * (
        .5 * (bet_sin_iy * denomalf + bet_sin_iy / betmdl1 * (cot_meas[ix] - cot_meas[iy])))

    return beta_i, alfa_i, betaline, alfaline

#---------------------------------------------------------------------------------------------------
#--- Helper / Debug Functions
#---------------------------------------------------------------------------------------------------

def tilt_slice_matrix(matrix, slice_shift, slice_width, tune=0):
    """Tilts and slices the ``matrix``

    Tilting means shifting each column upwards one step more than the previous columnns, i.e.

    a a a a a       a b c d
    b b b b b       b c d e
    c c c c c  -->  c d e f
    ...             ...
    y y y y y       y z a b
    z z z z z       z a b c

    """

    invrange = matrix.shape[0] - 1 - np.arange(matrix.shape[0])
    matrix[matrix.shape[0] - slice_shift:,:slice_shift] += tune
    matrix[:slice_shift, matrix.shape[1] - slice_shift:] -= tune
    return np.roll(matrix[np.arange(matrix.shape[0]), circulant(invrange)[invrange]],
                          slice_shift, axis=0)[:slice_width]



def printMatrix(debugfile, M, name):
    debugfile.write("begin Matrix " + name + "\n" + str(M.shape[0]) + " " + str(M.shape[1]) + "\n")

    np.savetxt(debugfile, M, fmt="%18.10e")
    debugfile.write("\nend\n")


def bad_phase(phi):
    modphi = phi % BADPHASE
    return (modphi < MOD_POINTFIVE_LOWER or modphi > MOD_POINTFIVE_UPPER)

    
def is_small(x):
    return abs(x) < ZERO_THRESHOLD

#---------------------------------------------------------------------------------------------------
# ---------- LOGGING stuff -------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------

logger_box_value_format = "={:.<36s}{:<24s} ="
logger_box_format = "={:<60s} ="
logger_boxedge_format = "= " * 28
logger_info = "{:s} {:<s}"


def _info_box_(string):
    LOGGER.info(" " + logger_box_format.format(string))

def _info_value_box_(key, value):
    LOGGER.info(logger_box_value_format.format(key, value))

def _debug_value_box_(key, value):
    LOGGER.debug(logger_box_value_format.format(key, value))

def _info_(string, prefix=" "):
    LOGGER.info(logger_info.format(prefix, string))

def _debug_(string):
    LOGGER.debug(logger_info.format(" ", string))

def _box_edge_():
    LOGGER.info(logger_boxedge_format)

def _error_(message):
    LOGGER.error(">>>" + message)

def _warning_(message):
    LOGGER.warning(message)
