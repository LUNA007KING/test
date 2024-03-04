from apscheduler.schedulers.background import BackgroundScheduler
from service.blockchain_service import update_blockchain_data

def start_scheduler():
    scheduler = BackgroundScheduler()
    # 比如每小时执行一次 update_blockchain_data
    scheduler.add_job(update_blockchain_data, 'interval', hours=1)
    scheduler.start()
