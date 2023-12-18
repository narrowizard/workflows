from typing import List

from chat.ask_codebase.assistants.directory_structure.relevant_file_finder import (
    RelevantFileFinder,
)
from chat.ask_codebase.tools.file_list_util import verify_file_list


OBJECTIVE_PROMPT = """
Identify a suitable reference test file that can be used as a guide for writing test cases
for the function {function_name}, located in the file {file_path}. 
The reference should provide a clear example of best practices in testing functions of a similar nature.
"""


def find_reference_tests(
    root_path: str, function_name: str, file_path: str
) -> List[str]:
    """Find reference tests for a specified function

    Args:
        root_path (str): The path to the root directory of the codebase.
        function_name (str): The name of the function to generate test cases for.
        file_path (str): The path to the file containing the target function for which test cases will be generated.

    Returns:
        List[str]: A list of paths to files that may contain a reference test for the specified function.
    """
    finder = RelevantFileFinder(root_path=root_path)
    objective = OBJECTIVE_PROMPT.format(
        function_name=function_name, file_path=file_path
    )
    test_paths = finder.analyze(objective)
    return verify_file_list(test_paths, root_path)
