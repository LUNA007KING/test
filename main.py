import logging
from service.blockchain_service import *
# from scheduler import start_scheduler
from db.database_manager import DatabaseManager
from config.settings import DB_CONFIG

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)



def main():
    initialize_database()
    update_blockchain_data()
    # start_scheduler()




if __name__ == '__main__':
    main()
