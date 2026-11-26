import glob
import re
from bs4 import BeautifulSoup
from collections import defaultdict

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
DAY_TO_IDX = {d: i for i, d in enumerate(DAYS)}
SLOTS = [
    "09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00", "12:00 - 13:00",
    "13:00 - 14:00", "14:00 - 15:00", "15:00 - 16:00", "16:00 - 17:00", "17:00 - 18:00"
]

def parse_room_loc_taxonomy(rn):
    """
    Exact Stage 4.4 taxonomy:
    - Block C: 'Advanced Electrical & Electronics Lab Room No-C105', 'C-006', 'C- 007', 'C-015', 'C-202', 'C-203', 'C-204'
    - Lab Block: '301 - Lab Block', '302', '303', '304', '307', '308', '402', '403', '404'
    - Lab Block (F): 'F-102 -Lab Block', 'F-103', 'F-104', 'F-105', 'F-106', 'F-112', 'F-113'
    - Law Block (E): 'Law Block E-301' to 'E-306', 'Law Block E-403', 'Law Block E-404'
    - UNKNOWN: 'X-Gen Innovation Lab (LAB Block)', 'NO_ROOM'
    """
    clean_r = rn.replace("Room no : ", "").strip()
    b, fl = "UNKNOWN", -1
    if "Law Block" in clean_r or "E-" in clean_r:
        b = "Law Block (E)"
        m = re.search(r'E-(\d)(\d{2})', clean_r)
        if m: fl = int(m.group(1))
    elif "F-" in clean_r:
        b = "Lab Block (F)"
        m = re.search(r'F-(\d)(\d{2})', clean_r)
        if m: fl = int(m.group(1))
    elif "Lab Block" in clean_r:
        b = "Lab Block"
        m = re.search(r'(\d)(\d{2})', clean_r)
        if m: fl = int(m.group(1))
    elif clean_r.startswith("C-") or "C105" in clean_r:
        b = "Block C"
        m = re.search(r'C-?\s*(\d)(\d{2})', clean_r)
        if m: fl = int(m.group(1))
    return b, fl

MEGA_TRACK_SECTIONS = [
    "CSE_TIGERS_2024", "CSE_RHINOS_2024", "CSE_PANTHERS_2024", "BIC_ TIGERS_2024",
    "AIML_ TIGERS_2024", "AIML_RHINOS_2024", "AIML_PANTHERS_2024", "AIML_LEOPARDS_2024",
    "AIML_WHALES_2024", "DS_ TIGERS_2024",
    "CSE_TIGERS_2023", "CSE_RHINOS_2023", "CSE_PANTHERS_2023", "AIML_TIGERS_2023",
    "AIML_RHINOCERS_2023", "AIML_PANTHERS_ 2023", "DS_TIGERS_ 2023", "BIC_TIGERS_ 2023"
]

MEGA_TRACK_FACULTY = [
    "Dr. Ravi Kiran Kummamuru",
    "Prof. Geeta Tripathi",
    "Dr T Santhosh Kumar",
    "Dr. Karthick N"
]

def load_timetable_data(base_dir="."):
    groups_file = glob.glob(f"{base_dir}/*Groups.html")[0]
    rooms_file = glob.glob(f"{base_dir}/*Rooms.html")[0]
    teachers_file = glob.glob(f"{base_dir}/*Teachers.html")[0]

    with open(rooms_file, 'r', encoding='utf-8') as f:
        soup_rooms = BeautifulSoup(f.read(), 'html.parser')
    with open(groups_file, 'r', encoding='utf-8') as f:
        soup_groups = BeautifulSoup(f.read(), 'html.parser')
    with open(teachers_file, 'r', encoding='utf-8') as f:
        soup_teachers = BeautifulSoup(f.read(), 'html.parser')

    # 1. Parse Faculty Leaves (-x-)
    faculty_leaves = defaultdict(set)
    t_links = [a for a in soup_teachers.find_all('a', href=True) if a['href'].startswith('#table_')]
    for a in t_links:
        t_name = a.get_text().strip()
        t_table = soup_teachers.find('table', id=a['href'][1:])
        for r in t_table.find_all('tr'):
            th = r.find('th')
            if not th or th.get_text().strip() not in DAYS: continue
            d_idx = DAY_TO_IDX[th.get_text().strip()]
            col_pos = 0
            for td in r.find_all('td'):
                cspan = int(td.get('colspan', 1))
                txt = td.get_text().strip()
                if txt == '-x-':
                    for c in range(cspan):
                        faculty_leaves[t_name].add((d_idx, col_pos + c))
                col_pos += cspan

    # 2. Extract Room Events (595 events)
    r_links = [a for a in soup_rooms.find_all('a', href=True) if a['href'].startswith('#table_')]
    events = []
    event_id = 0

    for a in r_links:
        r_name = a.get_text().strip()
        r_table = soup_rooms.find('table', id=a['href'][1:])
        for r in r_table.find_all('tr')[1:6]:
            day = r.find('th').get_text().strip()
            d_idx = DAY_TO_IDX[day]
            col = 0
            for td in r.find_all('td'):
                cspan = int(td.get('colspan', 1))
                txt = td.get_text().strip()
                if txt not in ['---', '-x-']:
                    lines = [s.strip() for s in td.stripped_strings]
                    groups_raw = lines[0] if len(lines) > 0 else ""
                    faculty_raw = lines[1] if len(lines) > 1 else ""
                    subject = lines[2] if len(lines) > 2 else ""

                    sections = [g.strip() for g in groups_raw.split(',') if g.strip()]
                    faculty = [f.strip() for f in re.split(r',', faculty_raw) if f.strip()]

                    bldg, floor = parse_room_loc_taxonomy(r_name)
                    events.append({
                        'event_id': event_id,
                        'subject': subject,
                        'room': r_name,
                        'building': bldg,
                        'floor': floor,
                        'baseline_day': d_idx,
                        'baseline_slot': col,
                        'duration': cspan,
                        'is_lab': (cspan == 2),
                        'sections': sections,
                        'faculty': faculty,
                        'is_pinned': False
                    })
                    event_id += 1
                col += cspan

    # 3. Add the 3 unassigned events
    events.append({
        'event_id': event_id,
        'subject': 'Basic Electrical and Electronics Engineering Theory',
        'room': 'NO_ROOM',
        'building': 'UNKNOWN',
        'floor': -1,
        'baseline_day': 1, # Tuesday
        'baseline_slot': 6,
        'duration': 1,
        'is_lab': False,
        'sections': ['ECE_TIGERS_2026'],
        'faculty': ['Dr. S Bhanu Prakash'],
        'is_pinned': True
    })
    event_id += 1

    events.append({
        'event_id': event_id,
        'subject': 'Basic Electrical and Electronics Engineering Theory',
        'room': 'NO_ROOM',
        'building': 'UNKNOWN',
        'floor': -1,
        'baseline_day': 4, # Friday
        'baseline_slot': 1,
        'duration': 1,
        'is_lab': False,
        'sections': ['ECE_TIGERS_2026'],
        'faculty': ['Dr. S Bhanu Prakash'],
        'is_pinned': True
    })
    event_id += 1

    events.append({
        'event_id': event_id,
        'subject': '2023-2027, 2024-2028Entrepreneurship Track, Research Track & Industry Track Theory',
        'room': 'NO_ROOM',
        'building': 'UNKNOWN',
        'floor': -1,
        'baseline_day': 2, # Wednesday
        'baseline_slot': 6,
        'duration': 2,
        'is_lab': True,
        'sections': list(MEGA_TRACK_SECTIONS),
        'faculty': list(MEGA_TRACK_FACULTY),
        'is_pinned': True
    })
    event_id += 1

    return {
        'events': events,
        'faculty_leaves': faculty_leaves,
        'days': DAYS,
        'slots': SLOTS
    }

if __name__ == "__main__":
    data = load_timetable_data(".")
    print(f"Loaded {len(data['events'])} events.")
    print("Slot 4 is:", data['slots'][4])
