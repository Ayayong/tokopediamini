@echo off
set BASE=C:\Users\ASUS\OneDrive\Documents\tokopedia-microservices

start "User 8001" cmd /k "cd /d %BASE%\user-service && python -m uvicorn main:app --reload --port 8001"
start "Product 8002" cmd /k "cd /d %BASE%\product-service && python -m uvicorn main:app --reload --port 8002"
start "Order 8003" cmd /k "cd /d %BASE%\order-service && python -m uvicorn main:app --reload --port 8003"
start "Payment 8004" cmd /k "cd /d %BASE%\payment-service && python -m uvicorn main:app --reload --port 8004"
start "Notification 8005" cmd /k "cd /d %BASE%\notification-service && python -m uvicorn main:app --reload --port 8005"
start "Gateway 8000" cmd /k "cd /d %BASE%\api-gateway && python -m uvicorn main:app --reload --port 8000"
start "Website 5173" cmd /k "cd /d %BASE%\frontend && npm.cmd run dev"