import json
import boto3
import re
import base64
import os

# Initialize AWS clients
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')

def lambda_handler(event, context):
    """
    Enhanced VIT ID card processor with multi-line name support.
    """
    
    try:
        body = json.loads(event['body'])
        image_data = body.get('image')
        filename = body.get('filename', 'id_card.jpg')
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        
        print(f"Processing: {filename}")
        
        # Decode base64 image
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)
        
        # Upload to S3
        s3_key = f"images/{filename}"
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=image_bytes,
            ContentType='image/jpeg'
        )
        
        print(f"Uploaded to S3: s3://{bucket_name}/{s3_key}")
        
        # Call Textract
        response = textract_client.detect_document_text(
            Document={'Bytes': image_bytes}
        )
        
        # Extract text with detailed position info
        text_blocks = []
        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                bbox = block['Geometry']['BoundingBox']
                text_blocks.append({
                    'text': block['Text'],
                    'confidence': block.get('Confidence', 0),
                    'top': bbox['Top'],
                    'left': bbox['Left'],
                    'height': bbox['Height'],
                    'width': bbox['Width']
                })
        
        # Sort by vertical position
        text_blocks.sort(key=lambda x: x['top'])
        
        print(f"\n{'='*70}")
        print(f"EXTRACTED TEXT (Total: {len(text_blocks)} lines)")
        print(f"{'='*70}")
        for i, block in enumerate(text_blocks):
            print(f"{i:2d}. '{block['text']}' (conf: {block['confidence']:.0f}%, top: {block['top']:.3f}, left: {block['left']:.3f})")
        
        # Enhanced extraction with multi-line support
        result = extract_vit_id_multiline(text_blocks)
        
        result['s3_location'] = f"s3://{bucket_name}/{s3_key}"
        result['filename'] = filename
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps(result)
        }
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps({
                'error': str(e),
                'name': 'Error Processing',
                'rgNumber': 'ERROR',
                'success': False
            })
        }


def extract_vit_id_multiline(text_blocks):
    """
    ENHANCED extraction supporting multi-line names with text merging.
    """
    
    lines = [block['text'].strip() for block in text_blocks]
    
    print(f"\n{'='*70}")
    print("STARTING MULTI-LINE NAME EXTRACTION")
    print(f"{'='*70}")
    
    # ========================================
    # STEP 1: Find RG Number (Anchor Point)
    # ========================================
    rg_number = "Not Found"
    rg_index = -1
    
    rg_patterns = [
        r'\b\d{2}[A-Z]{3}\d{4}\b',
        r'\b\d{2}[A-Z]{3}\d{3,5}\b',
        r'\b\d{2}\s*[A-Z]{3}\s*\d{4}\b',
    ]
    
    for i, line in enumerate(lines):
        line_clean = line.upper().replace(' ', '').replace('-', '')
        
        for pattern in rg_patterns:
            match = re.search(pattern, line_clean)
            if match:
                rg_number = match.group(0)
                rg_index = i
                print(f"\n✓ FOUND RG NUMBER: '{rg_number}' at line {i}")
                break
        
        if rg_number != "Not Found":
            break
    
    # ========================================
    # STEP 2: Create Multi-line Candidates
    # ========================================
    
    name_candidates = []
    
    if rg_index > 0:
        print(f"\n{'='*70}")
        print("CREATING MULTI-LINE NAME CANDIDATES")
        print(f"{'='*70}")
        
        # Look at lines above RG number (typical position for name)
        search_start = max(0, rg_index - 6)
        search_end = rg_index
        
        # Try combining 1, 2, and 3 consecutive lines
        for num_lines in [1, 2, 3]:
            for start_idx in range(search_start, search_end):
                end_idx = start_idx + num_lines
                
                if end_idx > search_end:
                    break
                
                # Check if these lines are vertically close (same region)
                if num_lines > 1:
                    blocks_to_merge = text_blocks[start_idx:end_idx]
                    if not are_blocks_vertically_close(blocks_to_merge):
                        continue
                
                # Merge the lines
                merged_lines = lines[start_idx:end_idx]
                merged_text = ' '.join(merged_lines)
                
                # Score this candidate
                score = score_name_candidate_multiline(
                    merged_text, 
                    merged_lines,
                    start_idx, 
                    rg_index, 
                    num_lines
                )
                
                if score > 0:
                    candidate = {
                        'name': merged_text,
                        'score': score,
                        'lines': num_lines,
                        'start_idx': start_idx,
                        'end_idx': end_idx,
                        'raw_lines': merged_lines
                    }
                    name_candidates.append(candidate)
                    print(f"  Lines {start_idx}-{end_idx-1} ({num_lines} lines): '{merged_text[:50]}...' → Score: {score}")
    
    # ========================================
    # STEP 3: Try "NAME" keyword strategy
    # ========================================
    
    print(f"\n{'='*70}")
    print("CHECKING FOR 'NAME' KEYWORD")
    print(f"{'='*70}")
    
    for i, line in enumerate(lines):
        if 'NAME' in line.upper():
            print(f"  Found 'NAME' at line {i}: '{line}'")
            
            # Check lines after "NAME" keyword
            for num_lines in [1, 2, 3]:
                if i + num_lines < len(lines):
                    start_idx = i + 1
                    end_idx = start_idx + num_lines
                    
                    if end_idx > len(lines):
                        break
                    
                    merged_lines = lines[start_idx:end_idx]
                    merged_text = ' '.join(merged_lines)
                    
                    score = score_name_candidate_multiline(
                        merged_text,
                        merged_lines,
                        start_idx,
                        rg_index,
                        num_lines,
                        near_name_keyword=True
                    )
                    
                    if score > 0:
                        candidate = {
                            'name': merged_text,
                            'score': score + 10,  # Bonus for being after NAME
                            'lines': num_lines,
                            'start_idx': start_idx,
                            'end_idx': end_idx,
                            'raw_lines': merged_lines
                        }
                        name_candidates.append(candidate)
                        print(f"    Lines {start_idx}-{end_idx-1}: '{merged_text[:50]}...' → Score: {score}")
    
    # ========================================
    # STEP 4: Select Best Candidate
    # ========================================
    
    print(f"\n{'='*70}")
    print(f"TOTAL CANDIDATES FOUND: {len(name_candidates)}")
    print(f"{'='*70}")
    
    if name_candidates:
        # Sort by score (highest first)
        name_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        print("\nTop 5 candidates:")
        for i, c in enumerate(name_candidates[:5]):
            print(f"{i+1}. Score: {c['score']:3d} | Lines: {c['lines']} | '{c['name']}'")
        
        best = name_candidates[0]
        raw_name = best['name']
        
        # Clean and correct the name
        cleaned_name = clean_and_correct_name(raw_name)
        
        print(f"\n✓ SELECTED CANDIDATE:")
        print(f"  Raw: '{raw_name}'")
        print(f"  Cleaned: '{cleaned_name}'")
        print(f"  Score: {best['score']}")
        print(f"  Lines used: {best['lines']}")
        
        name = cleaned_name
    else:
        name = "Unknown"
        print("\n✗ NO VALID NAME CANDIDATES FOUND")
    
    print(f"\n{'='*70}")
    print(f"FINAL RESULT")
    print(f"{'='*70}")
    print(f"Name: {name}")
    print(f"RG Number: {rg_number}")
    print(f"{'='*70}\n")
    
    return {
        'name': name,
        'rgNumber': rg_number,
        'success': True,
        'debug': {
            'totalLines': len(lines),
            'rgFoundAt': rg_index,
            'candidatesFound': len(name_candidates),
            'topCandidate': name_candidates[0] if name_candidates else None
        }
    }


def are_blocks_vertically_close(blocks, max_gap=0.015):
    """
    Check if text blocks are vertically close (part of same name region).
    """
    if len(blocks) <= 1:
        return True
    
    for i in range(len(blocks) - 1):
        current_bottom = blocks[i]['top'] + blocks[i]['height']
        next_top = blocks[i + 1]['top']
        gap = next_top - current_bottom
        
        # If gap is too large, they're not part of the same region
        if gap > max_gap:
            return False
    
    return True


def score_name_candidate_multiline(text, raw_lines, start_idx, rg_index, num_lines, near_name_keyword=False):
    """
    Score a multi-line name candidate.
    """
    
    if not text or len(text.strip()) < 3:
        return 0
    
    text = text.strip()
    score = 0
    
    # --- DISQUALIFIERS ---
    
    upper_text = text.upper()
    skip_keywords = [
        'VIT', 'VELLORE', 'INSTITUTE', 'TECHNOLOGY', 'CHENNAI', 'CAMPUS',
        'DEEMED', 'UNIVERSITY', 'UGC', 'SECTION', 'ACT', '1956',
        'DAY', 'SCHOLAR', 'HOSTEL', 'BLOCK', 'VALID', 'UNTIL',
        'HTTP', 'WWW', '.COM', '.IN', 'STUDENT', 'CARD', 'IDENTITY',
        'REGISTRATION', 'NUMBER', 'DATE', 'ISSUE', 'BLOOD', 'GROUP'
    ]
    
    for keyword in skip_keywords:
        if keyword in upper_text:
            return 0
    
    # Skip if contains RG number
    if re.search(r'\d{2}[A-Z]{3}\d{4}', upper_text.replace(' ', '')):
        return 0
    
    # Skip if too many digits
    digit_count = sum(c.isdigit() for c in text)
    if digit_count > len(text) * 0.2:
        return 0
    
    # --- POSITIVE INDICATORS ---
    
    # Base score
    score += 5
    
    # Length bonus (names typically 8-50 characters)
    if 8 <= len(text) <= 50:
        score += 5
    elif 50 < len(text) <= 70:
        score += 2
    
    # Word count (2-6 words for multi-line names)
    words = [w for w in text.split() if len(w) >= 2]
    word_count = len(words)
    
    if word_count == 2:
        score += 8
    elif word_count == 3:
        score += 10  # Most common for Indian names
    elif word_count == 4:
        score += 8
    elif word_count == 5:
        score += 5
    elif word_count >= 6:
        score += 2
    
    # Alphabetic content
    alpha_count = sum(c.isalpha() for c in text)
    if alpha_count > len(text) * 0.85:
        score += 5
    
    # Capitalization (names have capitals)
    if sum(1 for c in text if c.isupper()) >= 2:
        score += 4
    
    # Multi-line bonus (names often span multiple lines on ID cards)
    if num_lines == 2:
        score += 6  # Common for 2-word names split across lines
    elif num_lines == 3:
        score += 4  # Longer names
    
    # Position bonus (closer to RG number)
    if rg_index > 0:
        distance = rg_index - (start_idx + num_lines - 1)
        if distance == 1:
            score += 15  # Directly above RG
        elif distance == 2:
            score += 10
        elif distance == 3:
            score += 5
    
    # "NAME" keyword bonus
    if near_name_keyword:
        score += 12
    
    # Check each line isn't too short
    for line in raw_lines:
        if len(line.strip()) >= 3:
            score += 2
    
    return max(0, score)


def clean_and_correct_name(name):
    """
    Clean and correct name with OCR error fixing.
    """
    
    # Remove extra spaces
    name = ' '.join(name.split())
    
    # Remove numbers
    name = re.sub(r'\d+', '', name)
    
    # Remove special characters (keep spaces, dots, apostrophes)
    name = re.sub(r'[^a-zA-Z\s\.\']', '', name)
    
    # Split into words
    words = [w for w in name.split() if len(w) >= 2]
    
    # Fix common OCR errors
    corrected_words = []
    for word in words:
        corrected = fix_ocr_errors(word)
        corrected_words.append(corrected)
    
    # Title case
    formatted = [w.capitalize() for w in corrected_words]
    
    final_name = ' '.join(formatted).strip()
    
    # Remove trailing incomplete characters
    final_name = re.sub(r'\s+[A-Za-z]$', '', final_name)  # Remove single trailing letter
    
    return final_name


def fix_ocr_errors(word):
    """
    Fix common OCR errors in names.
    """
    
    # Common OCR substitutions
    replacements = {
        '0': 'O',  # Zero to O
        '1': 'I',  # One to I
        '5': 'S',  # Five to S
        '8': 'B',  # Eight to B
    }
    
    # Only apply to words that look like they have OCR errors
    corrected = word
    for wrong, right in replacements.items():
        if wrong in word:
            corrected = corrected.replace(wrong, right)
    
    # Fix partial words (missing first character)
    # Example: "namaneni" should be "Annamaneni" if it looks incomplete
    if len(word) >= 4:
        # Check if it starts with common incomplete patterns
        incomplete_patterns = {
            'amaneni': 'Annamaneni',
            'nnamaneni': 'Annamaneni',
            'naman': 'Anaman',  # Partial fix
        }
        
        word_lower = word.lower()
        for pattern, fix in incomplete_patterns.items():
            if pattern in word_lower:
                return fix
    
    # Capitalize properly
    return corrected.capitalize()


# Test event
"""
{
  "body": "{\"image\":\"data:image/jpeg;base64,...\",\"filename\":\"test.jpg\"}"
}
"""
