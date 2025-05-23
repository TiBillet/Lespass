import subprocess
import json
import csv
from pathlib import Path

def get_dependencies_from_pyproject():
    """Extract dependencies from pyproject.toml"""
    with open('pyproject.toml', 'r') as f:
        content = f.read()
    
    # Simple parsing to extract dependencies
    dependencies = []
    in_dependencies_section = False
    in_dev_dependencies_section = False
    
    for line in content.split('\n'):
        if line.strip() == '[tool.poetry.dependencies]':
            in_dependencies_section = True
            in_dev_dependencies_section = False
            continue
        elif line.strip() == '[tool.poetry.group.dev.dependencies]':
            in_dependencies_section = False
            in_dev_dependencies_section = True
            continue
        elif line.strip().startswith('[') and line.strip().endswith(']'):
            in_dependencies_section = False
            in_dev_dependencies_section = False
            continue
        
        if in_dependencies_section or in_dev_dependencies_section:
            if '=' in line and not line.strip().startswith('#'):
                package = line.split('=')[0].strip()
                if package != 'python':  # Skip python itself
                    dependencies.append({
                        'name': package,
                        'dev': in_dev_dependencies_section
                    })
    
    return dependencies

def get_license_info(package_name):
    """Get license information for a package using pip show"""
    try:
        result = subprocess.run(
            ['pip', 'show', package_name], 
            capture_output=True, 
            text=True
        )
        
        if result.returncode != 0:
            return {
                'name': package_name,
                'license': 'Unknown',
                'version': 'Unknown',
                'summary': 'Package information not available',
                'home_page': 'Unknown'
            }
        
        output = result.stdout
        license_info = {'name': package_name}
        
        for line in output.split('\n'):
            if line.startswith('License:'):
                license_info['license'] = line.replace('License:', '').strip() or 'Not specified'
            elif line.startswith('Version:'):
                license_info['version'] = line.replace('Version:', '').strip()
            elif line.startswith('Summary:'):
                license_info['summary'] = line.replace('Summary:', '').strip()
            elif line.startswith('Home-page:'):
                license_info['home_page'] = line.replace('Home-page:', '').strip()
        
        # If license not found in pip show output
        if 'license' not in license_info:
            license_info['license'] = 'Not specified in package metadata'
            
        return license_info
    
    except Exception as e:
        return {
            'name': package_name,
            'license': f'Error: {str(e)}',
            'version': 'Unknown',
            'summary': 'Error retrieving package information',
            'home_page': 'Unknown'
        }

def generate_license_report(dependencies):
    """Generate a comprehensive license report"""
    report = []
    
    print(f"Analyzing licenses for {len(dependencies)} packages...")
    
    for dep in dependencies:
        package_name = dep['name']
        print(f"Processing {package_name}...")
        license_info = get_license_info(package_name)
        license_info['dev_dependency'] = dep['dev']
        report.append(license_info)
    
    return report

def save_report_to_csv(report, filename='license_audit_report.csv'):
    """Save the license report to a CSV file"""
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['name', 'version', 'license', 'dev_dependency', 'summary', 'home_page']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for package in report:
            writer.writerow(package)
    
    return filename

def analyze_license_compatibility(report):
    """Analyze license compatibility with the project's license (AGPLv3)"""
    # Define license compatibility groups
    compatible_licenses = [
        'AGPL', 'AGPLv3', 'GNU AGPL', 'GNU AGPLv3',
        'GPL', 'GPLv3', 'GNU GPL', 'GNU GPLv3',
        'LGPL', 'LGPLv3', 'GNU LGPL', 'GNU LGPLv3',
        'MIT', 'BSD', 'Apache', 'Apache 2.0', 'Apache-2.0',
        'Public Domain', 'CC0', 'ISC', 'Unlicense', 'Python Software Foundation License'
    ]
    
    potentially_incompatible = []
    unknown_licenses = []
    
    for package in report:
        license_text = package['license'].upper()
        
        if license_text == 'NOT SPECIFIED' or license_text == 'NOT SPECIFIED IN PACKAGE METADATA' or license_text == 'UNKNOWN':
            unknown_licenses.append(package)
        elif not any(compatible_lic.upper() in license_text for compatible_lic in compatible_licenses):
            potentially_incompatible.append(package)
    
    return {
        'potentially_incompatible': potentially_incompatible,
        'unknown_licenses': unknown_licenses
    }

def main():
    """Main function to run the license audit"""
    print("Starting license audit...")
    
    # Get dependencies from pyproject.toml
    dependencies = get_dependencies_from_pyproject()
    
    # Generate license report
    report = generate_license_report(dependencies)
    
    # Save report to CSV
    csv_file = save_report_to_csv(report)
    print(f"License report saved to {csv_file}")
    
    # Analyze license compatibility
    compatibility_analysis = analyze_license_compatibility(report)
    
    # Print summary
    print("\n=== LICENSE AUDIT SUMMARY ===")
    print(f"Total packages analyzed: {len(report)}")
    print(f"Packages with potentially incompatible licenses: {len(compatibility_analysis['potentially_incompatible'])}")
    print(f"Packages with unknown licenses: {len(compatibility_analysis['unknown_licenses'])}")
    
    if compatibility_analysis['potentially_incompatible']:
        print("\nPotentially incompatible licenses:")
        for package in compatibility_analysis['potentially_incompatible']:
            print(f"  - {package['name']} ({package['license']})")
    
    if compatibility_analysis['unknown_licenses']:
        print("\nPackages with unknown licenses:")
        for package in compatibility_analysis['unknown_licenses']:
            print(f"  - {package['name']}")
    
    print("\nDetailed information is available in the CSV report.")
    print("=== END OF LICENSE AUDIT ===")

if __name__ == "__main__":
    main()