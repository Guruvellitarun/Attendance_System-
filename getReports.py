import json
import boto3
import pymysql
import os
from datetime import datetime

def lambda_handler(event, context):
    """
    Retrieve all reports for a user.
    Handles both GET requests and OPTIONS (CORS preflight).
    """
    
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': ''
        }
    
    try:
        # Get user email from query parameters
        params = event.get('queryStringParameters') or {}
        user_email = params.get('email')
        
        print(f"Received request for email: {user_email}")
        
        if not user_email:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'GET,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Missing email parameter',
                    'message': 'Please provide email in query string'
                })
            }
        
        # Database configuration
        db_host = os.environ.get('DB_HOST')
        db_user = os.environ.get('DB_USER')
        db_password = os.environ.get('DB_PASSWORD')
        db_name = os.environ.get('DB_NAME')
        
        if not all([db_host, db_user, db_password, db_name]):
            print("ERROR: Database credentials not configured")
            # Return empty list if DB not configured (for testing)
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'GET,OPTIONS'
                },
                'body': json.dumps({
                    'success': True,
                    'reports': [],
                    'total': 0,
                    'message': 'Database not configured'
                })
            }
        
        # Connect to database
        connection = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            connect_timeout=5
        )
        
        print(f"Connected to database successfully")
        
        with connection.cursor() as cursor:
            # Fetch all reports for this user
            sql = """
                SELECT 
                    report_id,
                    date,
                    time,
                    total_students,
                    report_url,
                    created_at
                FROM reports
                WHERE user_email = %s
                ORDER BY created_at DESC
                LIMIT 100
            """
            
            cursor.execute(sql, (user_email,))
            results = cursor.fetchall()
            
            print(f"Found {len(results)} reports")
            
            # Format the results
            reports = []
            for row in results:
                report = {
                    'id': str(row[0]),
                    'date': row[1].strftime('%Y-%m-%d') if row[1] else '',
                    'time': str(row[2]) if row[2] else '',
                    'studentCount': int(row[3]) if row[3] else 0,
                    'downloadUrl': row[4] or '',
                    'createdAt': row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else ''
                }
                reports.append(report)
                print(f"  Report {report['id']}: {report['date']} - {report['studentCount']} students")
        
        connection.close()
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': json.dumps({
                'success': True,
                'reports': reports,
                'total': len(reports)
            })
        }
        
    except pymysql.MySQLError as e:
        print(f"Database error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return empty array instead of error for better UX
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': json.dumps({
                'success': False,
                'reports': [],
                'total': 0,
                'error': 'Database error',
                'message': str(e)
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': json.dumps({
                'success': False,
                'reports': [],
                'total': 0,
                'error': str(e)
            })
        }


# Test event for GET request
"""
{
  "httpMethod": "GET",
  "queryStringParameters": {
    "email": "user@vit.edu"
  }
}
"""
