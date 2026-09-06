import re
import sys

def clean_text(text):
    """Removes source tracking metadata blocks like ."""
    text = re.sub(r'\\', '', text)
    return text.strip()

def format_srt_time(time_str):
    """Converts 00:00:17.313 format to SRT style 00:00:17,313."""
    return time_str.replace('.', ',')

def convert_to_srt(input_file_path, output_file_path):
    with open(input_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    srt_entries = []
    current_start = None
    current_end = None
    current_text_lines = []
    
    # Regex pattern matching any timestamp block: [HH:MM:SS.mmm -> HH:MM:SS.mmm]
    timestamp_pattern = re.compile(r'\[(\d{2}:\d{2}:\d{2}\.\d{3})\s*->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\]')

    for line_num, original_line in enumerate(lines, 1):
        # 1. Clean the line of source markers and extract text
        line = clean_text(original_line)
        if not line:
            continue
            
        # 2. Check for timestamps within the line
        match = timestamp_pattern.search(line)
        
        if match:
            # If we already have a subtitle block building, save it before opening a new timestamp block
            if current_start and current_text_lines:
                text_content = " ".join(current_text_lines).strip()
                if text_content:
                    srt_entries.append((current_start, current_end, text_content))
                current_text_lines = []

            # Extract the new times
            current_start = format_srt_time(match.group(1))
            current_end = format_srt_time(match.group(2))
            
            # Remove the timestamp string entirely from the current text payload
            remaining_text = timestamp_pattern.sub('', line).strip()
            if remaining_text:
                current_text_lines.append(remaining_text)
                
        else:
            # If there's no timestamp on this line, it belongs to the previous active timestamp block
            if current_start:
                current_text_lines.append(line)

    # Add the final trailing subtitle block if one remains open
    if current_start and current_text_lines:
        text_content = " ".join(current_text_lines).strip()
        if text_content:
            srt_entries.append((current_start, current_end, text_content))

    # Write out the SRT formatted entries
    with open(output_file_path, 'w', encoding='utf-8') as f:
        for idx, (start, end, text) in enumerate(srt_entries, 1):
            f.write(f"{idx}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")

    print(f"Successfully converted! Generated {len(srt_entries)} subtitle blocks.")

if __name__ == "__main__":
    # Example usage: Change these file paths as needed
    input_filename = "synced_output.txt"
    output_filename = "synced_output.srt"
    
    try:
        convert_to_srt(input_filename, output_filename)
    except FileNotFoundError:
        print(f"Error: Could not find the file '{input_filename}'. Place it in the same folder as the script.")