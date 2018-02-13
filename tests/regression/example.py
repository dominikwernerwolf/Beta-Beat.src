import sys
import os
import regression
import compare_utils


MYSELF = os.path.abspath(__file__)
CURRENT_DIR = os.path.dirname(MYSELF)
ROOT = os.path.join(CURRENT_DIR, "..", "..")

TEST_CASES = (
    regression.TestCase(name="should_succeed",
                        script=MYSELF,
                        arguments=os.path.join(CURRENT_DIR, "_test_out_success"),
                        output=os.path.join(CURRENT_DIR, "_test_out_success"),
                        test_function=compare_utils.compare_dirs_with),
    regression.TestCase(name="should_fail",
                        script=MYSELF,
                        arguments=os.path.join(CURRENT_DIR, "_test_out_fail"),
                        output=os.path.join(CURRENT_DIR, "_test_out_fail"),
                        test_function=lambda dir1, dir2: False),
    regression.TestCase(name="should_raise",
                        script=MYSELF,
                        arguments="valid_string make_it_raise",
                        output=os.path.join(CURRENT_DIR, "_test_out_fail"),
                        test_function=compare_utils.compare_dirs_with),
)


def launch_examples():
    regression.launch_test_set(TEST_CASES, ROOT)


def _fake_test(input):
    # This should raise if len(input) > 2
    _, output = input
    os.mkdir(output)
    with open(os.path.join(output, "test_file.txt")) as test_file:
        test_file.write("This is a file!")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        launch_examples()
    _fake_test(sys.argv)
