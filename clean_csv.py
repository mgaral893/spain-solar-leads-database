#!/usr/bin/env python3
import os
import csv
import re
import html

INPUT_CSV = "instaladores_solares_espana.csv"
OUTPUT_CSV = "instaladores_solares_espana.csv"

DUMMY_EMAILS = [
    "tuemail@dominio.com", "info@tudominio.es", "tu@email.com", "email@domain.com",
    "correo@correo.com", "user@example.com", "info@ejemplo.com", "admin@domain.com",
    "test@test.com", "nombre@dominio.com", "ejemplo@ejemplo.com", "mail@example.com",
    "tuemail@empresa.com", "seo.jesusarteaga@gmail.com", "tu@email.com", "info@tudominio.es",
    "info@tudominio.com", "info@tudominio.es", "mail@domain.com", "tuemail@dominio.com"
]

def clean_company_name(name):
    if not name:
        return ""
    name = html.unescape(name)
    name = re.split(r"\||-|—|::", name)[0].strip()
    name = re.sub(r"<[^>]+>", "", name)
    name = name.strip("※ *•_#-()[]{}▷▶★✔")
    name = re.sub(r"\b202\d\b", "", name).strip()
    name = re.sub(r"^\d+\s*", "", name).strip()
    
    for phrase in ["Directorio de", "Los mejores", "Instaladores de", "Empresas de"]:
        if name.lower().startswith(phrase.lower()):
            name = name[len(phrase):].strip()
            
    # Resolve typical UTF-8 double-encoding artifacts
    name = name.replace("Ã³", "ó").replace("ã³", "ó").replace("Â·", "·").replace("ã³", "ó").replace("Ã¡", "á").replace("Ã©", "é").replace("Ã­", "í").replace("Ãº", "ú").replace("Ã±", "ñ").replace("Ã‘", "Ñ").replace("Ã", "á")
    name = " ".join([w.capitalize() for w in name.split()])
    return name

def clean_phone(phone):
    if not phone:
        return ""
    digits = "".join(re.findall(r"\d", phone))
    
    # Filter placeholder/mock phones
    if digits in ["999999999", "123456789", "000000000"]:
        return ""
        
    if digits.startswith("34") and len(digits) > 9:
        digits = digits[2:]
        
    if len(digits) == 9:
        return f"+34 {digits[0:3]} {digits[3:5]} {digits[5:7]} {digits[7:9]}"
    elif len(digits) > 9:
        return f"+34 {digits[-9:-6]} {digits[-6:-4]} {digits[-4:-2]} {digits[-2:]}"
    return phone.strip()

def clean_address(address):
    if not address:
        return ""
    address = html.unescape(address)
    
    # Detect code leakages
    code_indicators = [
        "{", "}", "[", "]", "class=", "id=", "href=", "src=", "menu-item", 
        "span", "div", "script", "function", "var ", "const ", "let ", "//#", 
        "/*", "*/", "import ", "document.", "window.", "elementor", "wpa_field",
        "margin:", "padding:", "display:", "color:", "z-index", "href"
    ]
    address_lower = address.lower()
    if any(ind in address_lower for ind in code_indicators):
        return ""
        
    address = re.sub(r"<[^>]+>", "", address)
    address = " ".join(address.split())
    address = address.strip(" ,.-:;()[]")
    
    # Clean double-encoding
    address = address.replace("Ã³", "ó").replace("ã³", "ó").replace("Â·", "·").replace("Ã¡", "á").replace("Ã©", "é").replace("Ã­", "í").replace("Ãº", "ú").replace("Ã±", "ñ").replace("Ã‘", "Ñ").replace("Ã", "á")
    address = " ".join([w.capitalize() for w in address.split()])
    return address

def is_valid_email(email):
    if not email:
        return False
    email = email.lower().strip()
    if email in DUMMY_EMAILS:
        return False
    if any(email.startswith(d.split("@")[0]) for d in DUMMY_EMAILS if "@" in d):
        if "dominio" in email or "example" in email:
            return False
    if any(email.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".js", ".css"]):
        return False
    return "@" in email

def clean_cif(cif):
    if not cif:
        return ""
    cif = cif.upper().replace(" ", "").replace("-", "").strip()
    if len(cif) == 9 and cif[0].isalpha():
        return cif
    return ""

def sanitize_csv():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: {INPUT_CSV} not found.")
        return
        
    cleaned_rows = []
    with open(INPUT_CSV, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        
        for row in reader:
            if len(row) < 10:
                continue
                
            name = clean_company_name(row[0])
            razon_social = clean_company_name(row[1])
            cif = clean_cif(row[2])
            email = row[3].strip() if is_valid_email(row[3]) else ""
            phone = clean_phone(row[4])
            web = row[5].strip()
            address = clean_address(row[6])
            province = row[7].strip()
            linkedin = row[8].strip()
            facebook = row[9].strip()
            
            # Skip rows with no valid name or contact information
            if len(name) > 2 and (email or phone):
                cleaned_rows.append([
                    name, razon_social, cif, email, phone,
                    web, address, province, linkedin, facebook
                ])
                
    # Sort by province
    cleaned_rows.sort(key=lambda x: x[7])
    
    # Save cleaned database back
    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Empresa", "Razón Social", "CIF", "Email", "Teléfono", 
            "Sitio Web", "Dirección", "Provincia", "LinkedIn", "Facebook"
        ])
        for r in cleaned_rows:
            writer.writerow(r)
            
    print(f"Sanitization complete! Saved {len(cleaned_rows)} premium records to {OUTPUT_CSV}")

if __name__ == "__main__":
    sanitize_csv()
