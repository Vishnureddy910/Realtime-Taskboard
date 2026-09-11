import time
from app.core.celery_app import celery_app

@celery_app.task(name="send_welcome_email")
def send_welcome_email(email: str):
    print(f"📨 Starting to send welcome email to {email}...")
    
    # Simulate a heavy, time-consuming process (like connecting to an email server)
    time.sleep(5) 
    
    print(f"✅ SUCCESSFULLY SENT welcome email to {email}!")
    return f"Email sent to {email}"