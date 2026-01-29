import os
import re
import random
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_DAIHOC = os.path.join(BASE_DIR, "daihoc.txt")
FILE_THPT = os.path.join(BASE_DIR, "thpt.txt")
GENERIC_FAKULTAS_PRODI = {
    "Faculty of Information Technology": [
        "Software Engineering", "Cybersecurity", "Computer Science", 
        "Information Systems", "Information Technology"
    ],
    "Faculty of Electrical Engineering": [
        "Electrical Engineering", "Electronics and Telecommunications", "Control and Automation"
    ],
    "Faculty of Mechanical Engineering": [
        "Mechanical Engineering", "Automotive Engineering", "Mechatronics"
    ],
    "Faculty of Business Administration": [
        "Business Administration", "Accounting", "Finance and Banking", "Marketing"
    ],
    "Faculty of Foreign Languages": [
        "English Language", "Chinese Language", "Japanese Language", "Korean Language"
    ]
}
GENERIC_JURUSAN_SMK = [
    "Computer Science", "Mathematics", "Physics", "Chemistry", "Biology", "Literature", "English"
]
_schools_cache = None

def parse_location(lokasi_str):
    """
    Extract city, state, zip dari string Lokasi
    Example: "Jl. Dr. Setiabudi No.229, Isola, Kec. Sukasari, Kota Bandung, Jawa Barat 40154"
    Returns: (city, state, zip)
    """
    city = ""
    state = ""
    zip_code = ""
    zip_match = re.search(r'(\d{5})\s*$', lokasi_str)
    if zip_match:
        zip_code = zip_match.group(1)
    lokasi_upper = lokasi_str.upper()
    states = {
        "HÀ NỘI": "Hà Nội",
        "HỒ CHÍ MINH": "TP. Hồ Chí Minh", 
        "TP. HỒ CHÍ MINH": "TP. Hồ Chí Minh",
        "ĐÀ NẴNG": "Đà Nẵng",
        "HẢI PHÒNG": "Hải Phòng",
        "CẦN THƠ": "Cần Thơ",
        "BÌNH DƯƠNG": "Bình Dương",
        "ĐỒNG NAI": "Đồng Nai"
    }
    
    for key, value in states.items():
        if key in lokasi_upper:
            state = value
            break
    city_patterns = [
        r'Quận\s+([A-Za-z0-9\s]+)',
        r'Huyện\s+([A-Za-z\s]+)',
        r'(Hà Nội|Hồ Chí Minh|Đà Nẵng|Cần Thơ|Hải Phòng)'
    ]
    
    for pattern in city_patterns:
        match = re.search(pattern, lokasi_str, re.IGNORECASE)
        if match:
            city = match.group(1).strip() if "Hà Nội" not in match.group(0) else "Hà Nội"
            break
    if not city:
        city = "Hà Nội"
    if not state:
        state = "Hà Nội"
    if not zip_code:
        zip_code = "100000"
        
    return city, state, zip_code

def parse_school_block(block):
    """
    Parse satu blok data sekolah dari txt
    Returns: dict atau None jika invalid
    """
    data = {}
    lines = block.strip().split('\n')
    
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            
            if key == 'nama' or key == 'name':
                data['name'] = value
            elif key == 'image2url' or key == 'logo':
                data['logo_url'] = value
            elif key == 'id':
                data['id'] = value
            elif key == 'lokasi' or key == 'location':
                data['lokasi'] = value
            elif key == 'lat':
                try:
                    data['lat'] = float(value)
                except:
                    data['lat'] = 0
            elif key == 'long':
                try:
                    data['long'] = float(value)
                except:
                    data['long'] = 0
    if not data.get('name') or not data.get('id'):
        return None
    if data.get('lat', 0) == 0 or data.get('long', 0) == 0:
        logging.warning(f"[school_data] Skipping {data.get('name')} - no coordinates")
        return None
    lokasi = data.get('lokasi', '')
    city, state, zip_code = parse_location(lokasi)
    data['city'] = city
    data['state'] = state
    data['zip'] = zip_code
    name_lower = data['name'].lower()
    if any(kw in name_lower for kw in ['smk', 'sma', 'man', 'high school']):
        data['type'] = 'sekolah'
    else:
        data['type'] = 'kampus'
    
    return data

def load_schools_from_file(filepath):
    """Load semua sekolah/kampus dari file txt"""
    schools = []
    
    if not os.path.exists(filepath):
        logging.error(f"[school_data] File not found: {filepath}")
        return schools
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        blocks = content.split('--------------------------------------------------')
        
        for block in blocks:
            if block.strip():
                school = parse_school_block(block)
                if school:
                    schools.append(school)
        
        logging.info(f"[school_data] Loaded {len(schools)} schools from {os.path.basename(filepath)}")
        
    except Exception as e:
        logging.error(f"[school_data] Error loading {filepath}: {e}")
    
    return schools

def load_all_schools(force_reload=False):
    """Load semua sekolah dan kampus, dengan caching"""
    global _schools_cache
    
    if _schools_cache is not None and not force_reload:
        return _schools_cache
    
    all_schools = []
    all_schools.extend(load_schools_from_file(FILE_DAIHOC))
    all_schools.extend(load_schools_from_file(FILE_THPT))
    
    _schools_cache = all_schools
    
    print(f"[school_data] Total loaded: {len(all_schools)} institutions")
    
    return all_schools

def get_random_school(school_type=None):
    """
    Get random school/kampus
    school_type: None (any), 'kampus', 'sekolah'
    """
    schools = load_all_schools()
    
    if not schools:
        logging.error("[school_data] No schools loaded!")
        return None
    
    if school_type:
        filtered = [s for s in schools if s.get('type') == school_type]
        if filtered:
            return random.choice(filtered)
    
    return random.choice(schools)

def get_school_by_id(school_id):
    """Get school by ID"""
    schools = load_all_schools()
    
    for school in schools:
        if school.get('id') == str(school_id):
            return school
    
    return None

def generate_fakultas_prodi():
    """Generate random fakultas dan prodi"""
    fakultas = random.choice(list(GENERIC_FAKULTAS_PRODI.keys()))
    prodi = random.choice(GENERIC_FAKULTAS_PRODI[fakultas])
    return fakultas, prodi

def generate_jurusan_smk():
    """Generate random jurusan SMK"""
    return random.choice(GENERIC_JURUSAN_SMK)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    schools = load_all_schools()
    print(f"\n=== Loaded {len(schools)} schools ===\n")
    
    for s in schools[:3]:
        print(f"Name: {s['name']}")
        print(f"  ID: {s['id']}")
        print(f"  City: {s['city']}, State: {s['state']}")
        print(f"  Lat: {s['lat']}, Long: {s['long']}")
        print(f"  Logo: {s.get('logo_url', 'N/A')[:50]}...")
        print()
    
    print("=== Random School ===")
    rand = get_random_school()
    if rand:
        print(f"{rand['name']} ({rand['type']})")
