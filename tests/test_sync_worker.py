import pytest
from sync_worker import SyncWorker
from database.models import init_db

def test_sync_worker_offline_detection(tmp_path):
    db_path = str(tmp_path / "sync_test.db")
    init_db(f"sqlite:///{db_path}")
    
    worker = SyncWorker(db_path, "http://localhost:8000", "test_token")
    
    # We want to test that if _check_internet returns False, it raises the exception
    # Instead of running the thread, we can call run() and let it hit the exception 
    # Or just test _check_internet directly.
    # To avoid infinite loop in run(), we will mock is_running to turn false after one loop.
    
    # Let's mock _check_internet to return False
    worker._check_internet = lambda: False
    
    error_caught = []
    
    def on_sync_finished(success, msg):
        worker.is_running = False # stop loop
        error_caught.append((success, msg))
        
    worker.sync_finished.connect(on_sync_finished)
    
    # Call run directly (synchronously) for testing
    worker.run()
    
    assert len(error_caught) > 0
    success, msg = error_caught[0]
    assert success is False
    assert "No Internet Connection" in msg

