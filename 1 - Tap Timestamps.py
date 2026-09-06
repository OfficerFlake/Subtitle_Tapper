import sys
import os
import pygame
import re
import shutil
from datetime import datetime

# --- CONFIGURATION ---
TEXT_FILE = "transcript.txt"
AUDIO_FILE = "audio.ogg"  
FONT_SIZE = 18             
WINDOW_SIZE = (1000, 500)   
# ---------------------

def format_time(ms):
    """Formats milliseconds into high-resolution hh:mm:ss.mmm"""
    if ms is None:
        return "--:--:--.---"
    
    millis = int(ms % 1000)
    seconds = int((ms / 1000) % 60)
    minutes = int((ms / (1000 * 60)) % 60)
    hours = int((ms / (1000 * 60 * 60)))
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"

def parse_time_str(time_str):
    """Converts hh:mm:ss.mmm or mm:ss.mmm back into total milliseconds"""
    try:
        parts = time_str.split(":")
        
        if len(parts) == 3:  # hh:mm:ss.mmm
            hours, minutes, rest = parts
            seconds, millis = rest.split(".")
            total_ms = (int(hours) * 3600000) + (int(minutes) * 60000) + (int(seconds) * 1000) + int(millis.ljust(3, '0')[:3])
            return total_ms
        elif len(parts) == 2:  # mm:ss.mmm
            minutes, rest = parts
            seconds, millis = rest.split(".")
            total_ms = (int(minutes) * 60000) + (int(seconds) * 1000) + int(millis.ljust(3, '0')[:3])
            return total_ms
        return None
    except Exception:
        return None

def load_text_file(filename):
    if not os.path.exists(filename):
        print(f"Error: {filename} not found.")
        with open(filename, "w", encoding="utf-8") as f:
            f.write("Line one text sample\nLine two text sample\nLine three text sample")
        print(f"Created a sample '{filename}'.")
    
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def load_prior_progress(output_filename, total_lines):
    """Reload prior progress mapped strictly by line index to support duplicate text lines"""
    progress = {}
    if os.path.exists(output_filename):
        print(f"Found existing tracking log '{output_filename}'. Importing timestamps by line index...")
        pattern = re.compile(r"^\[(\d{2}:\d{2}:\d{2}\.\d{3}) -> (\d{2}:\d{2}:\d{2}\.\d{3})\]\s*(.*)$")
        with open(output_filename, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if idx >= total_lines:
                    break
                match = pattern.match(line.strip())
                if match:
                    start_str, end_str, text = match.groups()
                    start_ms = parse_time_str(start_str)
                    end_ms = parse_time_str(end_str)
                    
                    has_data = (start_ms is not None and (start_ms > 0 or end_ms > 0))
                    progress[idx] = {
                        'start': start_ms if has_data else None,
                        'end': end_ms if has_data else None
                    }
    return progress

def get_exact_matching_indices(data):
    """Detects indices of cards that share the exact same start and end time"""
    from collections import defaultdict
    time_groups = defaultdict(list)
    
    for i, item in enumerate(data):
        if item['start'] is not None and item['end'] is not None:
            time_groups[(item['start'], item['end'])].append(i)
            
    overlapping = set()
    for indices in time_groups.values():
        if len(indices) > 1:
            for idx in indices:
                overlapping.add(idx)
                
    return overlapping

def find_closest_line_index(data, target_ms):
    """Finds the card index that best matches or precedes the target timecode"""
    best_idx = 0
    min_diff = float('inf')
    
    for idx, item in enumerate(data):
        start = item['start']
        end = item['end']
        
        if start is not None and end is not None:
            if start <= target_ms <= end:
                return idx
        
        if start is not None:
            diff = abs(start - target_ms)
            if diff < min_diff:
                min_diff = diff
                best_idx = idx
        elif end is not None:
            diff = abs(end - target_ms)
            if diff < min_diff:
                min_diff = diff
                best_idx = idx
                
    return best_idx

def render_wrapped_text(surface, text, font, color, x, y, max_width):
    """Wrap text dynamically if it runs over the text column width boundary"""
    words = text.split(' ')
    lines = []
    current_line = ""
    
    for word in words:
        test_line = current_line + " " + word if current_line else word
        if font.size(test_line)[0] < max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
        
    current_y = y
    for line in lines:
        text_surface = font.render(line, True, color)
        surface.blit(text_surface, (x, current_y))
        current_y += font.get_linesize()
    return current_y 

def render_row_3_columns(surface, prefix, item, font, color, y, max_text_width):
    """Renders data cleanly split across 3 column structures using hh:mm:ss.mmm"""
    start_str = f"[{format_time(item['start'])}]"
    start_surf = font.render(start_str, True, color)
    surface.blit(start_surf, (20, y))
    
    end_str = f"[{format_time(item['end'])}]"
    end_surf = font.render(end_str, True, color)
    end_x = WINDOW_SIZE[0] - end_surf.get_width() - 20
    surface.blit(end_surf, (end_x, y))
    
    display_text = f"{prefix} {item['text']}"
    final_y = render_wrapped_text(surface, display_text, font, color, 160, y, max_text_width)
    return final_y

def main():
    pygame.init()
    pygame.mixer.init()
    
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Audio/Text Time Syncer (High-Res 3-Column)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", FONT_SIZE)
    small_font = pygame.font.SysFont("Arial", 13)
    
    lines = load_text_file(TEXT_FILE)
    if not lines:
        print("Text file is empty.")
        return
        
    prior_progress = load_prior_progress("synced_output.txt", len(lines))
    
    data = []
    last_mapped_end_time = 0
    target_start_idx = 0  
    
    for idx, line in enumerate(lines):
        saved = prior_progress.get(idx, {'start': None, 'end': None})
        data.append({
            'text': line,
            'start': saved['start'],
            'end': saved['end']
        })
        if saved['start'] is not None and saved['end'] is not None:
            last_mapped_end_time = max(last_mapped_end_time, saved['end'])
            target_start_idx = idx
        
    current_idx = target_start_idx
    audio_loaded = False
    playing = False
    
    current_audio_time_ms = max(0, last_mapped_end_time - 3000)
    
    if os.path.exists(AUDIO_FILE):
        pygame.mixer.music.load(AUDIO_FILE)
        audio_loaded = True
        print(f"Loaded {AUDIO_FILE} successfully.")
    else:
        print(f"Warning: {AUDIO_FILE} not found. Running in TEXT-ONLY mode.")

    space_pressed = False
    input_mode = False
    input_buffer = ""

    overlapping_indices = get_exact_matching_indices(data)
    overlaps_dirty = False

    running = True
    while running:
        dt = clock.tick(60) 
        
        if audio_loaded and playing:
            current_audio_time_ms += dt
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
            # --- GO-TO TIME OVERLAY MODE ---
            elif input_mode:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        jump_ms = parse_time_str(input_buffer)
                        if jump_ms is not None:
                            current_audio_time_ms = max(0, jump_ms)
                            current_idx = find_closest_line_index(data, current_audio_time_ms)
                            
                            if audio_loaded:
                                pygame.mixer.music.play(start=current_audio_time_ms / 1000.0)
                                if not playing:
                                    pygame.mixer.music.pause()
                            print(f"Jumped timeline & selected card index {current_idx} via G-key to {format_time(current_audio_time_ms)}")
                        else:
                            print(f"Ignored invalid timecode format input: '{input_buffer}'")
                        input_mode = False
                        input_buffer = ""
                    elif event.key == pygame.K_ESCAPE:
                        input_mode = False
                        input_buffer = ""
                    elif event.key == pygame.K_BACKSPACE:
                        input_buffer = input_buffer[:-1]
                    else:
                        if event.unicode.isdigit() or event.unicode in (':', '.'):
                            input_buffer += event.unicode
            
            # --- MAIN ACTIONS NAVIGATION MODE ---
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    space_pressed = True
                    adjusted_start = max(0, current_audio_time_ms - 500)
                    data[current_idx]['start'] = adjusted_start
                    data[current_idx]['end'] = None
                    overlaps_dirty = True
                    
                elif event.key == pygame.K_RETURN:
                    if audio_loaded:
                        if playing:
                            pygame.mixer.music.pause()
                            playing = False
                        else:
                            pygame.mixer.music.play(start=current_audio_time_ms / 1000.0)
                            playing = True
                            
                elif event.key == pygame.K_w: 
                    if current_idx > 0:
                        current_idx -= 1
                        
                elif event.key == pygame.K_s: 
                    if current_idx < len(data) - 1:
                        current_idx += 1
                        
                elif event.key == pygame.K_g: 
                    input_mode = True
                    input_buffer = ""
                    
                elif event.key == pygame.K_n:
                    if overlapping_indices:
                        sorted_overlaps = sorted(list(overlapping_indices))
                        next_overlap = next((idx for idx in sorted_overlaps if idx > current_idx), None)
                        if next_overlap is None:
                            next_overlap = sorted_overlaps[0]  # Wrap around
                        current_idx = next_overlap
                        print(f"Jumped to overlapping card index {current_idx}")
                    else:
                        print("No overlapping cards found.")
                    
                elif event.key == pygame.K_j:
                    target_start = data[current_idx]['start']
                    if target_start is not None:
                        current_audio_time_ms = target_start
                        if audio_loaded:
                            pygame.mixer.music.play(start=current_audio_time_ms / 1000.0)
                            if not playing:
                                pygame.mixer.music.pause()
                        print(f"J-Key forced timeline jump to current line start: {format_time(current_audio_time_ms)}")
                    else:
                        print("Cannot jump! Selected line has no start timestamp mapped yet.")
                    
                elif event.key == pygame.K_LEFTBRACKET: 
                    data[current_idx]['start'] = current_audio_time_ms
                    overlaps_dirty = True
                    
                elif event.key == pygame.K_RIGHTBRACKET: 
                    data[current_idx]['end'] = current_audio_time_ms
                    overlaps_dirty = True
                
                elif event.key == pygame.K_BACKSPACE:
                    data[current_idx]['start'] = None
                    data[current_idx]['end'] = None
                    overlaps_dirty = True
                    print(f"Wiped all timestamps for active row card index {current_idx}")
                    
            elif event.type == pygame.KEYUP:
                if event.key == pygame.K_SPACE and space_pressed:
                    space_pressed = False
                    adjusted_end = max(0, current_audio_time_ms - 500)
                    data[current_idx]['end'] = adjusted_end
                    overlaps_dirty = True
                    if current_idx < len(data) - 1:
                        current_idx += 1

        # --- SCRUBBING ACCELERATIONS ---
        if not input_mode:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_a]: 
                current_audio_time_ms = max(0, current_audio_time_ms - 150)
                if audio_loaded and playing:
                    pygame.mixer.music.play(start=current_audio_time_ms / 1000.0)
            if keys[pygame.K_d]: 
                current_audio_time_ms += 150
                if audio_loaded and playing:
                    pygame.mixer.music.play(start=current_audio_time_ms / 1000.0)

        if overlaps_dirty:
            overlapping_indices = get_exact_matching_indices(data)
            overlaps_dirty = False

        # --- UI DRAWING STAGE ---
        screen.fill((30, 30, 30))
        max_text_w = WINDOW_SIZE[0] - 320 
        
        status_text = f"Time: {format_time(current_audio_time_ms)} | Playing: {playing}"
        status_surface = font.render(status_text, True, (200, 200, 200))
        screen.blit(status_surface, (20, 20))
        
        next_y = 100
        
        # Render Previous Line (If exists)
        if current_idx > 0:
            p_idx = current_idx - 1
            p_item = data[p_idx]
            has_both = p_item['start'] is not None and p_item['end'] is not None
            if has_both:
                p_color = (128, 0, 0) if p_idx in overlapping_indices else (46, 204, 113) # Maroon if exact match, else Green
            else:
                p_color = (110, 110, 110)
            next_y = render_row_3_columns(screen, "Prev:", p_item, font, p_color, next_y, max_text_w)
            next_y += 20
            
        # Render Active Line Focus
        curr_item = data[current_idx]
        has_both_curr = curr_item['start'] is not None and curr_item['end'] is not None
        if space_pressed:
            c_color = (255, 50, 50)     # Red if space bar is held
        elif has_both_curr:
            c_color = (128, 0, 0) if current_idx in overlapping_indices else (52, 152, 219) # Maroon if exact match, else Blue
        elif curr_item['start'] is not None and curr_item['end'] is None:
            c_color = (241, 196, 15)    # Yellow layout status if only start is mapped
        else:
            c_color = (255, 215, 0)     # Standard Gold outline fallback focus
            
        next_y = render_row_3_columns(screen, "-->  ", curr_item, font, c_color, next_y, max_text_w)
        next_y += 30
        
        # Render Next Line Preview (If exists)
        if current_idx < len(data) - 1:
            n_idx = current_idx + 1
            next_item = data[n_idx]
            has_both_next = next_item['start'] is not None and next_item['end'] is not None
            if has_both_next:
                n_color = (128, 0, 0) if n_idx in overlapping_indices else (46, 204, 113) # Maroon if exact match, else Green
            else:
                n_color = (110, 110, 110)
            render_row_3_columns(screen, "Next:", next_item, font, n_color, next_y, max_text_w)

        # STATIC SHORTCUTS DISPLAY
        shortcuts = [
            "Enter: Play/Pause Audio",
            "Space (Hold/Rel): Sync Mapping (-0.5s)",
            "Backspace: Delete Current Timestamps",
            "A / D: Seek Time Timeline",
            "W / S: Select Text Row",
            "N: Jump to Next Overlap",
            "[ / ]: Precise Start/End Pinpoint Override",
            "J: Jump timeline to current line Start",
            "G: Go-To Timecode Jump"
        ]
        shortcut_start_y = WINDOW_SIZE[1] - 195
        for i, text in enumerate(shortcuts):
            sc_surf = small_font.render(text, True, (150, 150, 150))
            align_x = WINDOW_SIZE[0] - sc_surf.get_width() - 20
            screen.blit(sc_surf, (align_x, shortcut_start_y + (i * 16)))

        # PROGRESS BAR 
        bar_x, bar_y = 20, WINDOW_SIZE[1] - 40
        bar_w = WINDOW_SIZE[0] - 40
        bar_h = 16
        
        total_items = len(data)
        block_w = bar_w / total_items
        
        for idx, item in enumerate(data):
            bx = bar_x + (idx * block_w)
            has_both = item['start'] is not None and item['end'] is not None
            is_overlap = idx in overlapping_indices
            
            if idx == current_idx and (space_pressed or item['end'] is None):
                color = (241, 196, 15)  # Highlight bar indicator block yellow during hold recording
            elif has_both:
                color = (128, 0, 0) if is_overlap else (46, 204, 113)  # Maroon if exact match, else Green
            elif item['start'] is not None:
                color = (241, 196, 15)  
            else:
                color = (60, 60, 60)     
                
            pygame.draw.rect(screen, color, (bx, bar_y, max(1, block_w - 1), bar_h))

        if input_mode:
            overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 220))
            screen.blit(overlay, (0,0))
            prompt_surf = font.render("Enter timecode (hh:mm:ss.mmm) & press Enter:", True, (255, 255, 255))
            val_surf = font.render(input_buffer + "_", True, (0, 255, 0))
            screen.blit(prompt_surf, (150, 150))
            screen.blit(val_surf, (150, 200))

        pygame.display.flip()

    pygame.quit()
    
    # --- SAVE AND BACKUP PROCEDURE ---
    if os.path.exists("synced_output.txt"):
        print("\n--- Generating Progress Backup ---")
        timestamp_str = datetime.now().strftime("%y_%m_%d_%H_%M_%S")
        backup_filename = f"backup_{timestamp_str}.txt"
        
        try:
            shutil.copy("synced_output.txt", backup_filename)
            print(f"Successfully copied old session state to '{backup_filename}'")
        except Exception as e:
            print(f"Warning: Could not create backup file due to error: {e}")

    print("\n--- Saving Timestamps ---")
    with open("synced_output.txt", "w", encoding="utf-8") as f:
        for item in data:
            start_str = format_time(item['start']) if item['start'] is not None else "00:00:00.000"
            end_str = format_time(item['end']) if item['end'] is not None else "00:00:00.000"
            f.write(f"[{start_str} -> {end_str}] {item['text']}\n")
    print("Saved adjustments directly to synced_output.txt!")

if __name__ == "__main__":
    main()