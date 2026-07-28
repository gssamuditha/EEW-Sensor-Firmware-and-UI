import os
import re

TARGET_DIR = r"f:\Engineering Internship\EEW-Sensor-Firmware-and-UI\frontend\src"

REPLACEMENTS = {
    r'\bbg-white\b': 'bg-white dark:bg-slate-800',
    r'\bborder-gray-200\b': 'border-gray-200 dark:border-slate-700',
    r'\bborder-gray-100\b': 'border-gray-100 dark:border-slate-700',
    r'\bborder-gray-300\b': 'border-gray-300 dark:border-slate-600',
    r'\bbg-gray-50\b': 'bg-gray-50 dark:bg-slate-900',
    r'\bbg-gray-100\b': 'bg-gray-100 dark:bg-slate-800',
    r'\bbg-gray-200\b': 'bg-gray-200 dark:bg-slate-700',
    r'\btext-gray-500\b': 'text-gray-500 dark:text-slate-400',
    r'\btext-gray-400\b': 'text-gray-400 dark:text-slate-500',
    r'\btext-gray-600\b': 'text-gray-600 dark:text-slate-300',
    r'\btext-gray-700\b': 'text-gray-700 dark:text-slate-200',
    r'\btext-primary\b': 'text-primary dark:text-blue-400',
    r'\bbg-primary\b': 'bg-primary dark:bg-blue-600',
}

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    for pattern, replacement in REPLACEMENTS.items():
        # Negative lookahead to prevent double replacement (e.g. if dark:bg-slate-800 is already there)
        # We assume if the exact replacement is already there, we don't need to replace.
        # It's easier to just do a smart regex: match class, but only if not followed by dark: variant.
        # Actually a simple replace is fine if we only run it once.
        content = re.sub(pattern + r'(?! dark:)', replacement, content)

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

for root, _, files in os.walk(TARGET_DIR):
    for file in files:
        if file.endswith('.jsx') or file.endswith('.js'):
            process_file(os.path.join(root, file))

print("Done.")
