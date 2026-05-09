#!/usr/bin/env python3
"""
API网关模拟器
使用Python标准库实现
"""
import http.server
import socketserver
import json
import urllib.parse
import threading
import time
from datetime import datetime, timedelta
import hashlib
import hmac
import base64
from typing import Dict, List, Any, Callable, Optional
import re
import random


class RequestRateLimiter:
    """请求速率限制器"""
    
    def __init__(self, max_requests: int = 100, window_size: int = 60):
        self.max_requests = max_requests
        self.window_size = window_size
        self.clients = {}  # client_ip -> [request_times]
        self.lock = threading.Lock()
    
    def is_allowed(self, client_ip: str) -> bool:
        """检查客户端是否被允许发送请求"""
        with self.lock:
            now = time.time()
            
            if client_ip not in self.clients:
                self.clients[client_ip] = []
            
            # 清理窗口外的请求记录
            self.clients[client_ip] = [
                req_time for req_time in self.clients[client_ip]
                if now - req_time <= self.window_size
            ]
            
            # 检查是否超出限制
            if len(self.clients[client_ip]) >= self.max_requests:
                return False
            
            # 记录当前请求
            self.clients[client_ip].append(now)
            return True


class APISecurity:
    """API安全组件"""
    
    def __init__(self):
        self.api_keys = {}  # 存储有效的API密钥
        self.blocked_ips = set()  # 被阻止的IP地址
        self.security_rules = []  # 安全规则
    
    def add_api_key(self, key: str, permissions: List[str] = None):
        """添加API密钥"""
        self.api_keys[key] = {
            'permissions': permissions or ['read', 'write'],
            'created_at': datetime.now().isoformat()
        }
    
    def verify_api_key(self, key: str, required_permission: str = 'read') -> bool:
        """验证API密钥"""
        if key not in self.api_keys:
            return False
        
        permissions = self.api_keys[key]['permissions']
        return required_permission in permissions
    
    def add_security_rule(self, rule_func: Callable[[Dict], bool]):
        """添加安全规则"""
        self.security_rules.append(rule_func)
    
    def check_security(self, request_data: Dict) -> bool:
        """检查安全规则"""
        for rule in self.security_rules:
            if not rule(request_data):
                return False
        return True


class MockAPIService:
    """模拟API服务"""
    
    def __init__(self, name: str, latency_range: tuple = (0.1, 0.5)):
        self.name = name
        self.latency_range = latency_range
        self.response_templates = {}
        self.call_count = 0
        self.lock = threading.Lock()
    
    def register_endpoint(self, path: str, method: str, response_template: Dict):
        """注册端点"""
        key = f"{method.upper()}:{path}"
        self.response_templates[key] = response_template
    
    def call(self, path: str, method: str, params: Dict = None, body: Dict = None) -> Dict:
        """调用API服务"""
        with self.lock:
            self.call_count += 1
        
        # 模拟延迟
        delay = random.uniform(*self.latency_range)
        time.sleep(delay)
        
        key = f"{method.upper()}:{path}"
        template = self.response_templates.get(key)
        
        if not template:
            return {
                'error': 'Endpoint not found',
                'status_code': 404,
                'service': self.name
            }
        
        # 生成响应
        response = template.copy()
        response['service'] = self.name
        response['call_id'] = f"{self.name}-{self.call_count}"
        response['timestamp'] = datetime.now().isoformat()
        
        return response


class APIGateway:
    """API网关主类"""
    
    def __init__(self, port: int = 8000):
        self.port = port
        self.services = {}  # 服务名 -> MockAPIService
        self.routes = {}    # 路径 -> 服务名
        self.rate_limiter = RequestRateLimiter()
        self.security = APISecurity()
        self.middleware = []  # 中间件列表
        self.request_logs = []
        self.metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'blocked_requests': 0
        }
        self.lock = threading.Lock()
    
    def register_service(self, service: MockAPIService):
        """注册服务"""
        self.services[service.name] = service
    
    def add_route(self, path: str, service_name: str):
        """添加路由"""
        self.routes[path] = service_name
    
    def add_middleware(self, middleware_func: Callable):
        """添加中间件"""
        self.middleware.append(middleware_func)
    
    def process_request(self, path: str, method: str, headers: Dict, body: str = None) -> Dict:
        """处理请求"""
        client_ip = headers.get('X-Forwarded-For', 'unknown')
        
        # 检查速率限制
        if not self.rate_limiter.is_allowed(client_ip):
            with self.lock:
                self.metrics['blocked_requests'] += 1
            return {'error': 'Rate limit exceeded', 'status_code': 429}, 429
        
        # 检查安全规则
        request_data = {
            'path': path,
            'method': method,
            'headers': headers,
            'body': body
        }
        
        if not self.security.check_security(request_data):
            with self.lock:
                self.metrics['blocked_requests'] += 1
            return {'error': 'Security violation', 'status_code': 403}, 403
        
        # 验证API密钥
        api_key = headers.get('Authorization', '').replace('Bearer ', '')
        if api_key and not self.security.verify_api_key(api_key):
            return {'error': 'Invalid API key', 'status_code': 401}, 401
        
        # 查找路由
        service_name = None
        for route_path, svc_name in self.routes.items():
            if path.startswith(route_path):
                service_name = svc_name
                break
        
        if not service_name or service_name not in self.services:
            return {'error': 'Service not found', 'status_code': 404}, 404
        
        service = self.services[service_name]
        
        # 解析参数
        parsed_params = {}
        if '?' in path:
            _, query_string = path.split('?', 1)
            parsed_params = dict(urllib.parse.parse_qsl(query_string))
        
        body_data = None
        if body:
            try:
                body_data = json.loads(body)
            except:
                body_data = body
        
        # 调用服务
        try:
            response = service.call(path, method, parsed_params, body_data)
            status_code = response.get('status_code', 200)
            
            with self.lock:
                self.metrics['total_requests'] += 1
                if status_code < 400:
                    self.metrics['successful_requests'] += 1
                else:
                    self.metrics['failed_requests'] += 1
            
            return response, status_code
            
        except Exception as e:
            with self.lock:
                self.metrics['failed_requests'] += 1
            return {'error': str(e), 'status_code': 500}, 500
    
    def log_request(self, client_ip: str, path: str, method: str, status_code: int, duration: float):
        """记录请求日志"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'client_ip': client_ip,
            'path': path,
            'method': method,
            'status_code': status_code,
            'duration': duration
        }
        self.request_logs.append(log_entry)
        
        # 限制日志数量
        if len(self.request_logs) > 1000:
            self.request_logs = self.request_logs[-500:]
    
    def get_metrics(self) -> Dict:
        """获取指标"""
        with self.lock:
            return self.metrics.copy()
    
    def get_request_logs(self, limit: int = 100) -> List[Dict]:
        """获取请求日志"""
        return self.request_logs[-limit:]


class GatewayHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP请求处理器"""
    
    def __init__(self, gateway: APIGateway, *args, **kwargs):
        self.gateway = gateway
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        self.handle_request('GET')
    
    def do_POST(self):
        self.handle_request('POST')
    
    def do_PUT(self):
        self.handle_request('PUT')
    
    def do_DELETE(self):
        self.handle_request('DELETE')
    
    def handle_request(self, method: str):
        start_time = time.time()
        
        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else None
        
        # 处理请求
        response, status_code = self.gateway.process_request(
            self.path, method, dict(self.headers), body
        )
        
        # 计算处理时间
        duration = time.time() - start_time
        
        # 记录日志
        client_ip = self.client_address[0]
        self.gateway.log_request(client_ip, self.path, method, status_code, duration)
        
        # 发送响应
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        self.wfile.write(json.dumps(response, indent=2).encode('utf-8'))


class GatewayServer:
    """网关服务器"""
    
    def __init__(self, gateway: APIGateway):
        self.gateway = gateway
        self.server = None
        self.thread = None
    
    def start(self):
        """启动服务器"""
        handler = lambda *args, **kwargs: GatewayHTTPRequestHandler(self.gateway, *args, **kwargs)
        self.server = socketserver.TCPServer(("", self.gateway.port), handler)
        
        print(f"API网关服务器启动在端口 {self.gateway.port}")
        
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
    
    def stop(self):
        """停止服务器"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()


def main():
    """主函数演示"""
    # 创建API网关
    gateway = APIGateway(port=8080)
    
    # 注册一些模拟服务
    user_service = MockAPIService("user-service", latency_range=(0.05, 0.15))
    user_service.register_endpoint("/users", "GET", {
        "users": [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"}
        ],
        "total": 2
    })
    user_service.register_endpoint("/users/{id}", "GET", {
        "user": {"id": "{id}", "name": "Test User", "email": "test@example.com"}
    })
    gateway.register_service(user_service)
    
    product_service = MockAPIService("product-service", latency_range=(0.1, 0.2))
    product_service.register_endpoint("/products", "GET", {
        "products": [
            {"id": 1, "name": "Laptop", "price": 999.99},
            {"id": 2, "name": "Phone", "price": 599.99}
        ],
        "total": 2
    })
    product_service.register_endpoint("/products/{id}", "GET", {
        "product": {"id": "{id}", "name": "Test Product", "price": 199.99}
    })
    gateway.register_service(product_service)
    
    # 添加路由
    gateway.add_route("/api/users", "user-service")
    gateway.add_route("/api/products", "product-service")
    
    # 添加API密钥
    gateway.security.add_api_key("valid-key-123", ["read", "write"])
    gateway.security.add_api_key("read-only-key-456", ["read"])
    
    # 添加安全规则
    def block_suspicious_paths(request_data):
        suspicious_patterns = [r'<script', r'javascript:', r'union select', r'drop table']
        path = request_data.get('path', '').lower()
        body = str(request_data.get('body', '')).lower()
        
        combined = path + body
        for pattern in suspicious_patterns:
            if re.search(pattern, combined):
                return False
        return True
    
    gateway.security.add_security_rule(block_suspicious_paths)
    
    print("=== API网关模拟器演示 ===")
    print("可用端点:")
    print("  GET  /api/users - 获取用户列表")
    print("  GET  /api/users/{id} - 获取特定用户")
    print("  GET  /api/products - 获取产品列表")
    print("  GET  /api/products/{id} - 获取特定产品")
    print("")
    print("测试命令:")
    print("  curl -H 'Authorization: Bearer valid-key-123' http://localhost:8080/api/users")
    print("  curl -H 'Authorization: Bearer read-only-key-456' http://localhost:8080/api/products")
    print("")
    
    # 启动服务器
    server = GatewayServer(gateway)
    server.start()
    
    try:
        print("服务器正在运行... 按 Ctrl+C 停止")
        while True:
            time.sleep(1)
            
            # 每隔10秒打印一次指标
            if int(time.time()) % 10 == 0:
                metrics = gateway.get_metrics()
                print(f"指标 - 总请求: {metrics['total_requests']}, "
                      f"成功: {metrics['successful_requests']}, "
                      f"失败: {metrics['failed_requests']}, "
                      f"被阻止: {metrics['blocked_requests']}")
    
    except KeyboardInterrupt:
        print("\n正在关闭服务器...")
        server.stop()


if __name__ == "__main__":
    main()