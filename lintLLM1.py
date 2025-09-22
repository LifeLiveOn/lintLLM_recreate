"""
Optimized Verilog Code Analysis with LLM
Uses helper utilities for better code organization and readability
"""
import json
import os
import requests
from utils import Timer, validate_file_path, format_result_message, build_verilog_path, Config, parse_llm_result, write_to_csv


# Load reserved words once at startup
try:
    with open('reservewords', 'r', encoding='utf-8') as f:
        RESERVED_WORDS = f.read()
except FileNotFoundError:
    print("Warning: reservewords file not found. Using empty string.")
    RESERVED_WORDS = ""


def create_llm_request_data(context: str) -> dict:
    """Create the data payload for LLM API request"""
    think_disable = " /no_think"
    return {
        "model": Config.MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a verilog code defect checker and are able to follow the defined rules."},
            {"role": "user", "content": context + think_disable}
        ],
        "max_tokens": Config.MAX_TOKENS,
        "temperature": Config.TEMPERATURE,
        "stream": False,
    }


def send_llm_request(context: str) -> dict:
    """Send request to LLM and handle response"""
    data = create_llm_request_data(context)

    try:
        response = requests.post(
            Config.OLLAMA_API,
            headers=Config.HEADERS,
            data=json.dumps(data),
            timeout=Config.TIMEOUT
        )

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Request failed with status code: {response.status_code}"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Network request failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


def build_analysis_prompt(module_name: str, verilog_code_lines: list) -> str:
    """Build the complete analysis prompt for the LLM"""
    prompt_intro = f'The following <code> is the Verilog code for the module named <{module_name}>.'

    prompt_rules = f'''Please check this <code> step by step using the following steps and rules.
        step 1: Identify punctuation marks
            (1) chinese punctuation cannot appear in the code.
        step 2: Identify module
            (1) Module must be wrapped by 'module-endmodule'.
        step 3: Identify statements
            (1) For statements in the module header, end with (','), and do not punctuate the last statement.
            (2) For statements outside the module header, end with (';').
        step 4: Identify variables
            (1) For variables defined in the module header, the port type ('input', 'output', 'inout') must be defined.
                a. For 'input' type variables, they must be assigned to other variables.
                b. For 'output' type variables, they need to be assigned values by other variables.
                c. For 'inout' type variables, they can be assigned to other variables or assigned to other variables.
            (2) For variables not defined in the module header, the port type ('input', 'output', 'inout') cannot be defined.
            (3) For each variable, the data type ('wire', 'reg') must be defined.
                a. For variables of type 'wire', to be used in combinatorial logic.
                b. For variables of type 'reg', to be used in temporal logic.
                c. The default data type for variables is 'wire'.
            (4) For each variable, declare the bit-width ([MSB:LSB], which satisfies MSB>LSB), the default bit-width is 1, which can be omitted.
                a. Variable of bit width 1 ([0:0]) cannot be declared.
                b. For variables with a bit-width greater than 1, use the process to match the bit-width of the variable involved in the operation, neither exceeding the index nor leaving the bit-width free.
            (5) For assigning Values to Variable.
                a. To comply with the bit width requirements, distinguishing between binary, octal and hexadecimal mechanisms; each bit of octal represents three bits of binary, and each bit of hexadecimal represents four bits of binary.
                b. Cannot have an indefinite state ('x','X') or a highly resistive state ('z','Z').
            (6) Each variable is to be used.
        step 5: Identify 'always' block
            (1) The 'always' block should be wrapped with 'begin-end'.
            (2) Identify 'always' types.
                a. Temporal logic.
                b. Combinational logic.
            (3) Identify sensitive lists.
                a. Sensitive list of temporal logic.
                    ① Each signal in the sensitive list should have a 'posedge' edge or a 'negedge' edge.
                    ② For the judgment signal in the if condition, the original signal is used for the 'posedge' edge and the negative signal is used for the 'negedge' edge.
                    ③ Use ('or',',') to connect multiple signals in the sensitive list.
                    ④ All signals used in the sensitive list should be listed.
                b. Sensitive list of combinatorial logic.
                    ① Signals in the sensitive list cannot have a 'posedge' or 'negedge' edge.
                    ② Multiple signals in the sensitive list are connected by ('or',',').
                    ③ All signals used should be listed in the sensitive list or replaced by ('*').
                c. Cannot mix signals with edges and signals without edges.
                d. Cannot include extraneous signals.
            (4) Identify the mode of assignment
                a. Non-blocking assignment ('<=') is used in temporal logic.
                b. The use of blocking assignment methods ('=') in combinational logic.
                c. Cannot mix non-blocking assignment methods ('<=') and blocking methods ('=').
        step 6: Identify 'begin-end' block
            (1) 'begin' and 'end' always occur in pairs.
            (2) For statements that execute one statement a time, 'begin-end' can be omitted.
            (3) For statements that execute more than one statement at a time, 'begin-end' cannot be omitted.
        step 7: Identify reserved words
            (1) verilog includes reserved words: {RESERVED_WORDS}
            (2) Cannot use reserved words as variable or module names.
            (3) Cannot use reserved words that do not exist in verilog.
        step 8: Identify race or hazard condition
            (1) In temporal logic, a variable cannot be read immediately after it is assigned a value in the same 'always' block.
            (2) In temporal logic, it is not possible to assign a value to the same variable in the same sensitive list of 'always' block.
        step 9: Identify 'case' structure
            (1) The 'case' structure should have a 'default' statement.
            (2) The 'case' structure should include all possible branches.
            (3) The 'case' structure should be wrapped in a 'case-endcase'.
        step 10: Identify instantiated modules
            (1) Module port instantiation methods.
                a. Connected by position.
                b. Connected by name.
                c. Cannot mix the two methods.
            (2) The number of modules instantiated should be the same as the number required in the code.
            (3) The port type ('input', 'output', 'inout'), data type ('wire', 'reg') and data bit width of the module instantiation should be the same.
            (4) Each port should be connected when instantiated, not floating.
        step 11: Identify operator
            (1) For the bitwise operators ('&', '|', '^', '~'), which are used for operations on multi-bit width variables.
            (2) For logical operators ('&&', '||', '!'), which are used for one-bit width variables.

        DEFECT CATEGORIES:
        When you find a defect, classify it into one of these specific categories:

        Simple Level Defects:
        1. SYNTAX_STRUCTURE - Basic syntax errors, missing semicolons, punctuation issues
        2. SIGNAL_USAGE - Incorrect signal assignments, unused signals, undefined signals
        3. SENSITIVITY_LIST - Issues with always block sensitivity lists, missing signals
        4. RESERVED_WORDS - Using Verilog reserved words incorrectly
        5. RACE_HAZARD - Race conditions, hazard conditions in temporal logic

        Medium Level Defects:
        6. PORT_TYPE - Incorrect port declarations (input/output/inout), port connection issues
        7. OPERATORS - Incorrect operator usage (bitwise vs logical), operator precedence issues
        8. MODULE_INSTANCES - Module instantiation errors, port mapping issues

        Complex Level Defects:
        9. LOGIC_SYNTHESIS - Logic that cannot be properly synthesized, complex logic errors
        10. COMBINATIONAL_SEQUENTIAL - Mixing combinational and sequential logic incorrectly
        11. BIT_WIDTH_USAGE - Bit width mismatches, incorrect bit width declarations

        MULTIPLE DEFECT ANALYSIS:
        If multiple defects are detected, perform priority analysis:
        step 1: Number all defects sequentially as D1, D2, D3, etc.
        step 2: For each defect, simulate fixing it and count remaining defects (N1, N2, N3...)
        step 3: The defect with the smallest remaining defect count is the main defect
        step 4: Report the main defect line and all defect lines

        OUTPUT FORMAT:
        If NO defects found:
        RESULT: [NO]

        If SINGLE defect found:
        RESULT: [YES]
        DEFECT LINE: [line number]
        DEFECT CATEGORY: [category name]
        DESCRIPTION: [brief overview]

        If MULTIPLE defects found:
        RESULT: [YES]
        MULTIPLE DEFECTS: [YES]
        ALL DEFECT LINES: [line1-line2-line3]
        MAIN DEFECT LINE: [primary line number]
        DEFECT CATEGORY: [category of main defect]
        DESCRIPTION: [brief overview of main defect]

        Keep descriptions concise - just overview, not detailed explanations.'''

    # Build the complete prompt with numbered code lines
    context = prompt_intro + "\n"
    for i, line in enumerate(verilog_code_lines):
        context += f"{i+1}: {line}"
    context += "\n" + prompt_rules

    return context


def analyze_verilog_module(module_name: str, base_path: str) -> dict:
    """
    Analyze a single Verilog module using LLM

    Args:
        module_name: Name of the module (e.g., 'simple_1')
        base_path: Base path to the Verilog files directory

    Returns:
        dict: Analysis result from LLM
    """
    verilog_path = build_verilog_path(base_path, module_name)

    # Check if file exists
    if not validate_file_path(verilog_path):
        return {"error": f"File not found: {verilog_path}"}

    try:
        # Read Verilog file
        with open(verilog_path, 'r', encoding='utf-8') as f:
            verilog_code_lines = f.readlines()

        # Build prompt and send to LLM
        context = build_analysis_prompt(module_name, verilog_code_lines)
        result = send_llm_request(context)
        return result

    except Exception as e:
        return {"error": f"File operation failed: {str(e)}"}


def process_module_batch(start_idx: int, end_idx: int, module_prefix: str, base_path: str) -> None:
    """
    Process a batch of modules (e.g., all simple_ modules)

    Args:
        start_idx: Starting module index (inclusive)
        end_idx: Ending module index (exclusive)
        module_prefix: Module name prefix (e.g., 'simple_')
        base_path: Base path to the Verilog files
    """
    batch_timer = Timer(f"{module_prefix} batch")
    start_time = batch_timer.start()
    print(f"Starting {module_prefix} batch analysis...")

    # Extract level from module_prefix (remove the trailing underscore)
    level = module_prefix.rstrip('_')
    csv_filename = "results.csv"

    for k in range(start_idx, end_idx):
        module_name = f"{module_prefix}{k}"
        file_name = f"{module_name}.v"

        # Time individual module analysis
        module_timer = Timer(module_name)
        module_start = module_timer.start()
        print(f"{module_start} {module_name} analysis begin", flush=True)

        # Analyze the module
        result = analyze_verilog_module(module_name, base_path)

        module_end, module_duration = module_timer.end()
        print(
            f"{module_end} {module_name} analysis end (Duration: {module_duration:.3f}s)", flush=True)

        # Parse result and write to CSV
        defect_line, defect_type, defect_description = parse_llm_result(result)
        write_to_csv(csv_filename, level, file_name, defect_line,
                     defect_type, defect_description)

        # Still show brief status in console
        status = "DEFECT FOUND" if defect_line else "NO DEFECTS" if defect_type == "NONE" else "ERROR"
        print(f"  -> {module_name}: {status}")

    batch_end, batch_duration = batch_timer.end()
    print(f"---> {batch_duration:.3f}s {module_prefix} batch completed")
    print(f"Results written to {csv_filename}")


def main():
    """Main function to orchestrate the entire analysis process"""
    print("Starting Verilog Code Analysis with LLM")
    print("=" * 60)

    total_timer = Timer("Total Analysis")
    total_timer.start()

    # Remove existing results file to start fresh
    csv_filename = "results.csv"
    if os.path.exists(csv_filename):
        os.remove(csv_filename)
        print(f"Removed existing {csv_filename}")

    # Process each category of modules
    for prefix, folder in zip(Config.PROJECT_PREFIXES, Config.FOLDER_NAMES):
        base_path = f"{Config.BASE_BENCHMARK_PATH}/{folder}"
        process_module_batch(
            Config.MODULE_START_INDEX,
            Config.MODULE_END_INDEX,
            prefix,
            base_path
        )
        print()  # Add spacing between batches

    _, total_duration = total_timer.end()
    print("=" * 60)
    print(f"Total Analysis Time: {total_duration:.3f}s")
    print(f"Results saved to: {csv_filename}")
    print("Analysis Complete!")


if __name__ == "__main__":
    main()
