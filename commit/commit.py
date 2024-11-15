# flake8: noqa: E402
import os
import re
import subprocess
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "libs"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "libs"))
sys.path.append(os.path.dirname(__file__))

from chatmark import Checkbox, Form, TextEditor  # noqa: E402
from ide_services import IDEService  # noqa: E402
from llm_api import chat_completion_stream  # noqa: E402

diff_too_large_message_en = (
    "Commit failed. The modified content is too long "
    "and exceeds the model's length limit. "
    "You can try to make partial changes to the file and submit multiple times. "
    "Making small changes and submitting them multiple times is a better practice."
)
diff_too_large_message_zh = (
    "提交失败。修改内容太长，超出模型限制长度，"
    "可以尝试选择部分修改文件多次提交，小修改多提交是更好的做法。"
)

COMMIT_PROMPT_LIMIT_SIZE = 20000


def _T(en_text, zh_text):
    """
    Returns a text in the current language.
    :param en_text: The English version of the text
    :param zh_text: The Chinese version of the text
    :return: The text in the current language
    """
    if IDEService().ide_language() == "zh":
        return zh_text
    else:
        return en_text


def extract_markdown_block(text):
    """
    Extracts the first Markdown code block from the given text without the language specifier.

    :param text: A string containing Markdown text
    :return: The content of the first Markdown code block, or None if not found
    """
    # 正则表达式匹配Markdown代码块，忽略可选的语言类型标记
    pattern = r"```(?:\w+)?\s*\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)

    if match:
        # 返回第一个匹配的代码块内容，去除首尾的反引号和语言类型标记
        # 去除块结束标记前的一个换行符，但保留其他内容
        block_content = match.group(1)
        return block_content
    else:
        return text


# Read the prompt from the diffCommitMessagePrompt.txt file
def read_prompt_from_file(filename):
    """
    Reads the content of a file and returns it as a string.

    This function is designed to read a prompt message from a text file.
    It expects the file to be encoded in UTF-8 and will strip any leading
    or trailing whitespace from the content of the file. If the file does
    not exist or an error occurs during reading, the function logs an error
    message and exits the script.

    Parameters:
    - filename (str): The path to the file that contains the prompt message.

    Returns:
    - str: The content of the file as a string.

    Raises:
    - FileNotFoundError: If the file does not exist.
    - Exception: If any other error occurs during file reading.
    """
    s = IDEService()
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        s.ide_logging(
            "info",
            f"File {filename} not found. "
            "Please make sure it exists in the same directory as the script.",
        )
        sys.exit(1)
    except Exception as e:
        s.ide_logging("info", f"An error occurred while reading the file {filename}: {e}")
        sys.exit(1)


# Read the prompt content from the file
script_path = os.path.dirname(__file__)
PROMPT_FILENAME = os.path.join(script_path, "diffCommitMessagePrompt.txt")
PROMPT_COMMIT_MESSAGE_BY_DIFF_USER_INPUT = read_prompt_from_file(PROMPT_FILENAME)
prompt_commit_message_by_diff_user_input_llm_config = {
    "model": os.environ.get("LLM_MODEL", "gpt-3.5-turbo-1106")
}


language = ""


def assert_value(value, message):
    """
    判断给定的value是否为True，如果是，则输出指定的message并终止程序。

    Args:
        value: 用于判断的值。
        message: 如果value为True时需要输出的信息。

    Returns:
        无返回值。

    """
    if value:
        print(message, file=sys.stderr, flush=True)
        sys.exit(-1)


def decode_path(encoded_path):
    octal_pattern = re.compile(r"\\[0-7]{3}")

    if octal_pattern.search(encoded_path):
        bytes_path = encoded_path.encode("utf-8").decode("unicode_escape").encode("latin1")
        decoded_path = bytes_path.decode("utf-8")
        return decoded_path
    else:
        return encoded_path


def get_modified_files():
    """
    获取当前修改文件列表以及已经staged的文件列表

    Args:
        无

    Returns:
        tuple: 包含两个list的元组，第一个list包含当前修改过的文件，第二个list包含已经staged的文件
    """
    """ 获取当前修改文件列表以及已经staged的文件列表"""
    output = subprocess.check_output(["git", "status", "-s", "-u"], text=True, encoding="utf-8")
    lines = output.split("\n")
    modified_files = []
    staged_files = []

    def strip_file_name(file_name):
        file = file_name.strip()
        if file.startswith('"'):
            file = file[1:-1]
        return file

    for line in lines:
        if len(line) > 2:
            status, filename = line[:2], decode_path(line[3:])
            # check wether filename is a directory
            if os.path.isdir(filename):
                continue
            modified_files.append((os.path.normpath(strip_file_name(filename)), status[1:2]))
            if status[0:1] == "M" or status[0:1] == "A" or status[0:1] == "D":
                staged_files.append((os.path.normpath(strip_file_name(filename)), status[0:1]))
    return modified_files, staged_files


def get_marked_files(modified_files, staged_files):
    """
    根据给定的参数获取用户选中以供提交的文件

    Args:
        modified_files (List[str]): 用户已修改文件列表
        staged_files (List[str]): 用户已staged文件列表

    Returns:
        List[str]: 用户选中的文件列表
    """
    # Create two Checkbox instances for staged and unstaged files
    staged_files_show = [f'{file[1] if file[1]!="?" else "U"} {file[0]}' for file in staged_files]
    staged_checkbox = Checkbox(staged_files_show, [True] * len(staged_files_show))

    unstaged_files = [file for file in modified_files if file[1].strip() != ""]
    unstaged_files_show = [
        f'{file[1] if file[1]!="?" else "U"} {file[0]}' for file in unstaged_files
    ]
    unstaged_checkbox = Checkbox(unstaged_files_show, [False] * len(unstaged_files_show))

    # Create a Form with both Checkbox instances
    form_list = []
    if len(staged_files) > 0:
        form_list.append("Staged:\n\n")
        form_list.append(staged_checkbox)

    if len(unstaged_files) > 0:
        form_list.append("Unstaged:\n\n")
        form_list.append(unstaged_checkbox)

    form = Form(form_list, submit_button_name="Continue")

    # Render the Form and get user input
    form.render()

    # Retrieve the selected files from both Checkbox instances
    staged_checkbox_selections = staged_checkbox.selections if staged_checkbox.selections else []
    unstaged_selections = unstaged_checkbox.selections if unstaged_checkbox.selections else []
    selected_staged_files = [staged_files[idx][0] for idx in staged_checkbox_selections]
    selected_unstaged_files = [unstaged_files[idx][0] for idx in unstaged_selections]

    return selected_staged_files, selected_unstaged_files


def rebuild_stage_list(staged_select_files, unstaged_select_files):
    """
    根据用户选中文件，重新构建stage列表

    Args:
        staged_select_files: 当前选中的已staged文件列表
        unstaged_select_files: 当前选中的未staged文件列表

    Returns:
        None
    """
    # 获取当前所有staged文件
    current_staged_files = subprocess.check_output(
        ["git", "diff", "--name-only", "--cached"], text=True
    ).splitlines()

    # 添加unstaged_select_files中的文件到staged
    for file in unstaged_select_files:
        subprocess.check_output(["git", "add", file])

    # 将不在staged_select_files中的文件从staged移除
    user_selected_files = staged_select_files + unstaged_select_files
    files_to_unstage = [file for file in current_staged_files if file not in user_selected_files]
    for file in files_to_unstage:
        subprocess.check_output(["git", "reset", file])


def get_diff():
    """
    获取暂存区文件的Diff信息

    Args:
        无

    Returns:
        bytes: 返回bytes类型，是git diff --cached命令的输出结果

    """
    return subprocess.check_output(["git", "diff", "--cached"])


def get_current_branch():
    try:
        # 使用git命令获取当前分支名称
        result = subprocess.check_output(
            ["git", "branch", "--show-current"], stderr=subprocess.STDOUT
        ).strip()
        # 将结果从bytes转换为str
        current_branch = result.decode("utf-8")
        return current_branch
    except subprocess.CalledProcessError:
        # 如果发生错误，打印错误信息
        return None
    except FileNotFoundError:
        # 如果未找到git命令，可能是没有安装git或者不在PATH中
        return None


def generate_commit_message_base_diff(user_input, diff):
    """
    根据diff信息，通过AI生成一个commit消息

    Args:
        user_input (str): 用户输入的commit信息
        diff (str): 提交的diff信息

    Returns:
        str: 生成的commit消息

    """
    global language
    language_prompt = "You must response commit message in chinese。\n" if language == "zh" else ""
    prompt = PROMPT_COMMIT_MESSAGE_BY_DIFF_USER_INPUT.replace("{__DIFF__}", f"{diff}").replace(
        "{__USER_INPUT__}", f"{user_input + language_prompt}"
    )

    model_token_limit_error = (
        diff_too_large_message_en if language == "en" else diff_too_large_message_zh
    )
    if len(str(prompt)) > COMMIT_PROMPT_LIMIT_SIZE:
        print(model_token_limit_error, flush=True)
        sys.exit(0)

    messages = [{"role": "user", "content": prompt}]
    response = chat_completion_stream(messages, prompt_commit_message_by_diff_user_input_llm_config)

    if (
        not response["content"]
        and response.get("error", None)
        and f'{response["error"]}'.find("This model's maximum context length is") > 0
    ):
        print(model_token_limit_error)
        sys.exit(0)

    assert_value(not response["content"], response.get("error", ""))
    response["content"] = extract_markdown_block(response["content"])
    return response


def display_commit_message_and_commit(commit_message):
    """
    展示提交信息并提交。

    Args:
        commit_message: 提交信息。

    Returns:
        None。

    """
    text_editor = TextEditor(commit_message, submit_button_name="Commit")
    text_editor.render()

    new_commit_message = text_editor.new_text
    if not new_commit_message:
        return None
    return subprocess.check_output(["git", "commit", "-m", new_commit_message])


def check_git_installed():
    try:
        subprocess.run(
            ["git", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        print("Git is not installed on your system.", file=sys.stderr, flush=True)
    except FileNotFoundError:
        print("Git is not installed on your system.", file=sys.stderr, flush=True)
    except Exception:
        print("Git is not installed on your system.", file=sys.stderr, flush=True)
    return False


def main():
    global language
    try:
        start_msg = _T("Let's follow the steps below.\n\n", "开始按步骤操作。\n\n")
        print(start_msg)
        # Ensure enough command line arguments are provided
        if len(sys.argv) < 2:
            print("Usage: python script.py <user_input>", file=sys.stderr, flush=True)
            sys.exit(-1)

        user_input = sys.argv[1]
        language = IDEService().ide_language()

        if not check_git_installed():
            sys.exit(-1)

        step1_msg = _T(
            "Step 1/2: Select the files you've changed that you wish to include in this commit, "
            "then click 'Submit'.",
            "第一步/2：选择您希望包含在这次提交中的文件，然后点击“提交”。",
        )
        print(step1_msg, end="\n\n", flush=True)
        modified_files, staged_files = get_modified_files()
        if len(modified_files) == 0:
            print("There are no files to commit.", flush=True)
            sys.exit(0)

        staged_select_files, unstaged_select_files = get_marked_files(modified_files, staged_files)
        if not staged_select_files and not unstaged_select_files:
            no_files_msg = _T(
                "No files selected, the commit has been aborted.",
                "没有选择任何文件，提交已中止。",
            )
            print(no_files_msg)
            return

        rebuild_stage_list(staged_select_files, unstaged_select_files)

        step2_msg = _T(
            "Step 2/2: Review the commit message I've drafted for you. "
            "Edit it below if needed. Then click 'Commit' to proceed with "
            "the commit using this message.",
            "第二步/2：查看我为您起草的提交消息。如果需要，请在下面编辑它。然后单击“提交”以使用此消息进行提交。",
        )
        print(step2_msg, end="\n\n", flush=True)
        diff = get_diff()
        branch_name = get_current_branch()
        if branch_name:
            user_input += "\ncurrent repo branch name is:" + branch_name
        commit_message = generate_commit_message_base_diff(user_input, diff)

        # TODO
        # remove Closes #IssueNumber in commit message
        commit_message["content"] = (
            commit_message["content"]
            .replace("Closes #IssueNumber", "")
            .replace("No specific issue to close", "")
            .replace("No specific issue mentioned.", "")
        )

        commit_result = display_commit_message_and_commit(commit_message["content"])
        if not commit_result:
            commit_abort_msg = _T(
                "Commit aborted.",
                "提交已中止。",
            )
            print(commit_abort_msg, flush=True)
        else:
            commit_completed_msg = _T(
                "Commit completed.",
                "提交已完成。",
            )
            print(commit_completed_msg, flush=True)
        sys.exit(0)
    except Exception as err:
        print("Exception:", err, file=sys.stderr, flush=True)
        sys.exit(-1)


if __name__ == "__main__":
    main()
