import re
import pandas as pd
from pathlib import Path
import pdfplumber
import os
from datetime import datetime

class EskomBillProcessor:
    def __init__(self):
        self.data = []
        
    def extract_value(self, text, pattern):
        """Extract value using regex pattern"""
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def clean_numeric_value(self, value):
        """Convert string to float, handling special cases"""
        if value is None or value == '-' or value == '':
            return 0.0
        try:
            # Remove commas and convert to float
            return float(value.replace(',', ''))
        except ValueError:
            print(f"Warning: Could not convert '{value}' to number, using 0")
            return 0.0

    def clean_customer_name(self, text):
        """Extract only the customer name without extra fields"""
        pattern = r'NAME\s+([\w,\s&]+?)(?:\s*FAX|\s*$)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def calculate_vat(self, total_charges):
        """Calculate VAT amount (15% of charges)"""
        try:
            return round(float(total_charges) * 0.15, 2)
        except:
            return None

    def extract_bill_data(self, text):
        """Extract all relevant data from bill text"""
        # Extract basic information
        account_number = self.extract_value(text, r'YOUR ACCOUNT NO\s+(\d+)')
        billing_date = self.extract_value(text, r'BILLING DATE\s+(\d{4}-\d{2}-\d{2})')
        invoice_number = self.extract_value(text, r'TAX INVOICE NO\s+(\d+)')
        account_month = self.extract_value(text, r'ACCOUNT MONTH\s+([A-Z]+ \d{4})')
        
        # Extract customer name (cleaned)
        customer_name = self.clean_customer_name(text)
        
        # Extract consumption and charges
        consumption_match = re.search(r'TOTAL ENERGY CONSUMED[^\d]+([\d,.]+)', text)
        consumption = float(consumption_match.group(1).replace(',', '')) if consumption_match else None
        
        # Extract network charge rate
        network_charge_match = re.search(r'Network Capacity Charge @ R([\d.]+) per day', text)
        network_rate = float(network_charge_match.group(1)) if network_charge_match else None
        
        # Extract total charges before VAT
        charges_pattern = r'TOTAL CHARGES FOR BILLING PERIOD\s+R\s+([\d,.-]+)'
        total_charges = self.extract_value(text, charges_pattern)
        if total_charges:
            total_charges = float(total_charges.replace(',', ''))
            vat_amount = self.calculate_vat(total_charges)
        else:
            vat_amount = None
            
        # Extract reading type
        reading_type = self.extract_value(text, r'READING TYPE:\s+(\w+)')
        
        return {
            'account_number': account_number,
            'billing_date': billing_date,
            'invoice_number': invoice_number,
            'account_month': account_month,
            'customer_name': customer_name,
            'consumption': consumption,
            'network_rate': network_rate,
            'total_charges': total_charges,
            'vat_amount': vat_amount,
            'reading_type': reading_type
        }

    def process_pdf(self, pdf_path):
        """Process a single PDF file"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = "\n".join(page.extract_text() for page in pdf.pages)
                
                # Extract raw values
                data = {
                    'account_number': self.extract_value(text, r'YOUR ACCOUNT NO\s+(\d+)'),
                    'billing_date': self.extract_value(text, r'BILLING DATE\s+(\d{4}-\d{2}-\d{2})'),
                    'invoice_number': self.extract_value(text, r'TAX INVOICE NO\s+(\d+)'),
                    'account_month': self.extract_value(text, r'ACCOUNT MONTH\s+([A-Z]+ \d{4})'),
                    'due_date': self.extract_value(text, r'(?:CURRENT )?DUE DATE\s+(\d{4}-\d{2}-\d{2})'),
                    'customer_name': self.extract_value(text, r'NAME\s+([\w,\s&]+)'),
                    'opening_reading': self.clean_numeric_value(self.extract_value(text, r'Opening Reading[^\d]+([\d,.]+|-)')),
                    'closing_reading': self.clean_numeric_value(self.extract_value(text, r'Closing Reading[^\d]+([\d,.]+|-)')),
                    'consumption': self.clean_numeric_value(self.extract_value(text, r'TOTAL ENERGY CONSUMED[^\d]+([\d,.]+|-)')),
                    'total_due': self.clean_numeric_value(self.extract_value(text, r'TOTAL AMOUNT DUE\s+R\s+([\d,.-]+)(?:CR)?')),
                    'network_charge': self.clean_numeric_value(self.extract_value(text, r'Network Capacity Charge[^\d]+([\d,.]+|-)')),
                    'energy_charge': self.clean_numeric_value(self.extract_value(text, r'Energy Charge[^\d]+([\d,.]+|-)')),
                }
                
                self.data.append(data)
                return True
                
        except Exception as e:
            print(f"Error processing {pdf_path}: {str(e)}")
            return False

    def export_to_csv(self, base_output_path):
        """Export extracted data to CSV with unique filename if original is locked"""
        if not self.data:
            print("No data to export")
            return False
        
        df = pd.DataFrame(self.data)
        
        # Format numeric columns
        numeric_columns = ['consumption', 'total_due', 'network_charge', 'energy_charge', 
                          'opening_reading', 'closing_reading']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Generate a unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name, file_ext = os.path.splitext(base_output_path)
        output_path = f"{file_name}_{timestamp}{file_ext}"
        
        try:
            df.to_csv(output_path, index=False, float_format='%.2f')
            print(f"Data exported to: {output_path}")
            return True
        except Exception as e:
            print(f"Error exporting data: {str(e)}")
            return False

    def process_directory(self, directory):
        """Process all PDF files in the given directory"""
        pdf_files = Path(directory).glob('*.pdf')
        success_count = 0
        
        for pdf_path in pdf_files:
            if self.process_pdf(pdf_path):
                success_count += 1
                print(f"Successfully processed: {pdf_path.name}")
        
        if success_count == 0:
            print("No PDF files were successfully processed")
        else:
            print(f"Successfully processed {success_count} PDF files")

def main():
    processor = EskomBillProcessor()
    
    # Get directory path
    pdf_dir = input("Enter directory path containing Eskom PDFs: ").strip() or os.getcwd()
    
    if not os.path.isdir(pdf_dir):
        print("Invalid directory path!")
        return
    
    # Process PDFs
    processor.process_directory(pdf_dir)
    
    # Try to export
    base_output_path = os.path.join(pdf_dir, "eskom_bills_processed.csv")
    processor.export_to_csv(base_output_path)

if __name__ == "__main__":
    main()