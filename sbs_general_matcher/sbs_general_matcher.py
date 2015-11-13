import __init__  # @UnusedImport
import os
import sys
import json
from matchers import phase_matcher, coupling_matcher
from SegmentBySegment import SegmentBySegment
from madx import madx_templates_runner

CURRENT_PATH = os.path.abspath(os.path.dirname(__file__))

MATCHER_TYPES = {
    "phase": phase_matcher.PhaseMatcher,
    "coupling": coupling_matcher.CouplingMatcher
}


def main(input_file_path):

    print "+++ Starting Segment by Segment Match +++"

    print "Preparing MAD-X script..."
    input_data = InputData(input_file_path)
    _run_madx_matching(input_data)
    for matcher in input_data.matchers:
        _write_sbs_data(str(matcher.ip),
                        matcher.match_data_b1.beam_match_path,
                        matcher.match_data_b2.beam_match_path,
                        matcher.match_data_b1.range_start_name,
                        matcher.match_data_b2.range_start_name,
                        )


def _run_madx_matching(input_data):
    extract_sequences_list = []
    set_initial_values_list = []
    constraints_aux_vals_list = []
    define_variables_list = []
    set_matching_macros_list = []
    gen_changeparameters_list = []
    apply_correction_list = []
    run_corrected_twiss_list = []
    for matcher in input_data.matchers:
        extract_sequences_list.append(matcher.extract_sequences())
        set_initial_values_list.append(matcher.set_initial_values())
        constraints_aux_vals_list.append(matcher.define_aux_values())
        define_variables_list.append(matcher.define_variables())
        set_matching_macros_list.append(matcher.set_matching_macros())
        gen_changeparameters_list.append(matcher.generate_changeparameters())
        apply_correction_list.append(matcher.apply_correction())
        run_corrected_twiss_list.append(matcher.run_corrected_twiss())
    madx_templates = madx_templates_runner.MadxTemplates(
        log_file=os.path.join(input_data.match_path, "log.out"),
        output_file=os.path.join(input_data.match_path, "resolved.madx"),
        madx_path="/afs/cern.ch/user/m/mad/bin/madx_dev64"
    )
    madx_templates.lhc_super_matcher_madx(
        input_data.lhc_mode,
        "\n".join(extract_sequences_list),
        "\n".join(set_initial_values_list),
        "\n".join(constraints_aux_vals_list),
        "\n".join(define_variables_list),
        "\n".join(set_matching_macros_list),
        "\n".join(gen_changeparameters_list),
        input_data.match_path,
        "\n".join(run_corrected_twiss_list),
    )


def _write_sbs_data(ip, beam1_temporary_path, beam2_temporary_path, range_beam1_start_name, range_beam2_start_name):
    save_path_b1 = os.path.join(beam1_temporary_path, "sbs")
    save_path_b2 = os.path.join(beam2_temporary_path, "sbs")
    input_data_b1 = SegmentBySegment._InputData(beam1_temporary_path)
    input_data_b2 = SegmentBySegment._InputData(beam2_temporary_path)
    prop_models_b1 = SegmentBySegment._PropagatedModels(save_path_b1, "IP" + str(ip))
    prop_models_b2 = SegmentBySegment._PropagatedModels(save_path_b2, "IP" + str(ip))

    SegmentBySegment.getAndWriteData("IP" + ip, input_data_b1, None, prop_models_b1, save_path_b1, False, False, True, False, "LHCB1", None)
    SegmentBySegment.getAndWriteData("IP" + ip, input_data_b2, None, prop_models_b2, save_path_b2, False, False, True, False, "LHCB2", None)


class InputData():
    def __init__(self, input_file_path):
        with open(input_file_path, "r") as input_file:
            input_data = InputData._byteify(json.load(input_file))
            self._check_and_assign_attribute(input_data, "lhc_mode")
            self._check_and_assign_attribute(input_data, "match_path")
            self.matchers = []
            if "matchers" in input_data:
                self._get_matchers_list(input_data)

    def _get_matchers_list(self, input_data):
        raw_matchers_list = input_data["matchers"]
        for matcher_name, matcher_data in raw_matchers_list.iteritems():
            for attribute_name in ["type", "ip", "beam1_path", "beam2_path",
                                   "use_errors", "propagation"]:
                InputData._check_attribute(matcher_name, matcher_data, attribute_name)
            matcher_type = matcher_data["type"]
            MatcherClass = MATCHER_TYPES.get(matcher_type, None)
            if MatcherClass is None:
                print >> sys.stderr, 'Unknown matcher type: ' + matcher_type + ' must be in: ' + MATCHER_TYPES.keys()
                sys.exit(-1)
            exclude_constr_string = ""
            if "exclude_constraints" in matcher_data:
                exclude_constr_string = matcher_data["exclude_constraints"]
            exclude_vars_string = ""
            if "exclude_variables" in matcher_data:
                exclude_vars_string = matcher_data["exclude_variables"]
            print "Successfully read matcher " + matcher_name
            self.matchers.append(MatcherClass(
                matcher_name, matcher_data["ip"],
                str(matcher_data["beam1_path"]), str(matcher_data["beam2_path"]),
                str(self.match_path),
                matcher_data["use_errors"], matcher_data["propagation"],
                exclude_constr_string, exclude_vars_string
            ))

    def _check_and_assign_attribute(self, input_data, attribute_name):
            InputData._check_attribute("input data", input_data, attribute_name)
            setattr(self, attribute_name, input_data[attribute_name])

    @staticmethod
    def _check_attribute(base_dict_name, base_dict, attribute_name):
        if not attribute_name in base_dict:
            print >> sys.stderr, 'Cannot find ' + attribute_name + ' attribute in ' + base_dict_name + '. Aborting.'
            sys.exit(-1)

    # This transforms annoying unicode string into common byte string
    @staticmethod
    def _byteify(input_data):
        if isinstance(input_data, dict):
            return dict([(InputData._byteify(key), InputData._byteify(value)) for key, value in input_data.iteritems()])
        elif isinstance(input_data, list):
            return [InputData._byteify(element) for element in input_data]
        elif isinstance(input_data, unicode):
            return input_data.encode('utf-8')
        else:
            return input_data


if __name__ == "__main__":
    main(os.path.abspath(os.path.join(CURRENT_PATH, "match_test", "input_test.json")))