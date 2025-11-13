import json
import boto3
import pymysql
import os
from datetime import datetime

def lambda_handler(event, context):
    """
    This function saves attendance records to RDS MySQL database.
    """
    
    try:
        # Parse incoming request
        body = json.loads(event['body'])
        attendance_data = body.get('attendanceData', [])
        date = body.get('date')
        time = body.get('time')
        user_email = body.get('userEmail')
        report_url = body.get('reportUrl', '')
        
        # Database configuration from environment variables
        db_host = os.environ.get('DB_HOST')
        db_user = os.environ.get('DB_USER')
        db_password = os.environ.get('DB_PASSWORD')
        db_name = os.environ.get('DB_NAME')
        
        # Connect to database
        connection = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            connect_timeout=5
        )
        
        print("Successfully connected to database")
        
        with connection.cursor() as cursor:
            # First, check if user exists, if not create
            user_check_sql = "SELECT user_id FROM users WHERE email = %s"
            cursor.execute(user_check_sql, (user_email,))
            user_exists = cursor.fetchone()
            
            if not user_exists:
                print(f"Creating new user: {user_email}")
                user_insert_sql = "INSERT INTO users (email, full_name) VALUES (%s, %s)"
                cursor.execute(user_insert_sql, (user_email, user_email.split('@')[0]))
            
            # Insert report record
            report_sql = """
                INSERT INTO reports (user_email, date, time, total_students, report_url, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            cursor.execute(report_sql, (
                user_email,
                date,
                time,
                len(attendance_data),
                report_url,
                datetime.now()
            ))
            
            report_id = cursor.lastrowid
            print(f"Created report with ID: {report_id}")
            
            # Insert individual attendance records
            attendance_sql = """
                INSERT INTO attendance (report_id, student_name, registration_number, date, time)
                VALUES (%s, %s, %s, %s, %s)
            """
            
            for student in attendance_data:
                cursor.execute(attendance_sql, (
                    report_id,
                    student.get('name'),
                    student.get('rgNumber'),
                    date,
                    time
                ))
            
            # Commit the transaction
            connection.commit()
            print(f"✅ Saved {len(attendance_data)} attendance records successfully")
        
        connection.close()
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps({
                'success': True,
                'reportId': report_id,
                'message': f'Successfully saved {len(attendance_data)} records'
            })
        }
        
    except pymysql.MySQLError as e:
        print(f"Database error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps({
                'error': 'Database error',
                'message': str(e)
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps({
                'error': str(e),
                'message': 'Failed to save to database'
            })
        }


# Example test event
"""
{
  "body": "{\"attendanceData\":[{\"name\":\"John Doe\",\"rgNumber\":\"21BCE1234\"}],\"date\":\"2024-11-08\",\"time\":\"10:30\",\"userEmail\":\"user@example.com\",\"reportUrl\":\"https://s3.amazonaws.com/report.csv\"}"
}
"""
