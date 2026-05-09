#!/usr/bin/env python3
"""
实时消息代理
使用Python标准库实现
"""
import json
import threading
import time
import queue
import socket
import select
import struct
from datetime import datetime
from typing import Dict, List, Callable, Optional
import hashlib
import hmac


class MessageQueue:
    """消息队列"""
    
    def __init__(self, name: str, max_size: int = 1000):
        self.name = name
        self.max_size = max_size
        self.messages = queue.Queue(maxsize=max_size)
        self.subscribers = []  # 存储订阅者回调
        self.message_count = 0
        self.created_at = datetime.now()
    
    def publish(self, message: Dict) -> bool:
        """发布消息到队列"""
        try:
            # 添加元数据
            enriched_message = message.copy()
            enriched_message['__timestamp'] = datetime.now().isoformat()
            enriched_message['__queue'] = self.name
            enriched_message['__msg_id'] = self.message_count
            
            # 尝试放入队列
            self.messages.put(enriched_message, block=False)
            self.message_count += 1
            
            # 通知所有订阅者
            for subscriber in self.subscribers:
                try:
                    subscriber(enriched_message)
                except Exception:
                    # 如果订阅者处理失败，继续处理其他订阅者
                    continue
            
            return True
        except queue.Full:
            return False
    
    def subscribe(self, callback: Callable[[Dict], None]):
        """订阅队列消息"""
        self.subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[Dict], None]):
        """取消订阅"""
        if callback in self.subscribers:
            self.subscribers.remove(callback)
    
    def get_message(self, timeout: float = None) -> Optional[Dict]:
        """获取消息（阻塞）"""
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def size(self) -> int:
        """获取队列大小"""
        return self.messages.qsize()


class TopicRouter:
    """主题路由器"""
    
    def __init__(self):
        self.topics = {}  # topic_name -> MessageQueue
        self.topic_patterns = {}  # 正则表达式模式 -> MessageQueue
        self.lock = threading.Lock()
    
    def create_topic(self, topic_name: str, max_size: int = 1000) -> MessageQueue:
        """创建主题"""
        with self.lock:
            if topic_name not in self.topics:
                self.topics[topic_name] = MessageQueue(topic_name, max_size)
            return self.topics[topic_name]
    
    def get_topic(self, topic_name: str) -> Optional[MessageQueue]:
        """获取主题"""
        return self.topics.get(topic_name)
    
    def route_message(self, topic: str, message: Dict) -> bool:
        """路由消息到相应主题"""
        topic_queue = self.get_topic(topic)
        if topic_queue:
            return topic_queue.publish(message)
        return False
    
    def register_pattern(self, pattern: str, queue: MessageQueue):
        """注册模式匹配"""
        import re
        compiled_pattern = re.compile(pattern)
        self.topic_patterns[compiled_pattern] = queue


class ClientSession:
    """客户端会话"""
    
    def __init__(self, client_socket: socket.socket, address: tuple):
        self.socket = client_socket
        self.address = address
        self.subscriptions = set()  # 订阅的主题
        self.connected_at = datetime.now()
        self.message_count = 0
        self.lock = threading.Lock()
    
    def send_message(self, message: Dict) -> bool:
        """向客户端发送消息"""
        try:
            serialized_msg = json.dumps(message).encode('utf-8')
            # 先发送消息长度，再发送消息内容
            msg_length = len(serialized_msg)
            self.socket.send(struct.pack('!I', msg_length))
            self.socket.send(serialized_msg)
            with self.lock:
                self.message_count += 1
            return True
        except Exception:
            return False
    
    def add_subscription(self, topic: str):
        """添加订阅"""
        with self.lock:
            self.subscriptions.add(topic)
    
    def remove_subscription(self, topic: str):
        """移除订阅"""
        with self.lock:
            self.subscriptions.discard(topic)


class MessageBroker:
    """消息代理主类"""
    
    def __init__(self, host: str = 'localhost', port: int = 9090):
        self.host = host
        self.port = port
        self.router = TopicRouter()
        self.sessions = {}  # socket -> ClientSession
        self.running = False
        self.server_socket = None
        self.selector = None
        self.stats = {
            'connections': 0,
            'disconnections': 0,
            'messages_sent': 0,
            'messages_received': 0
        }
        self.lock = threading.Lock()
    
    def start(self):
        """启动消息代理"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.server_socket.setblocking(False)
        
        self.selector = select.poll()
        self.selector.register(self.server_socket, select.POLLIN)
        
        self.running = True
        print(f"消息代理启动在 {self.host}:{self.port}")
        
        # 启动主循环
        self._run_event_loop()
    
    def stop(self):
        """停止消息代理"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        if self.selector:
            self.selector.unregister(self.server_socket)
    
    def _run_event_loop(self):
        """运行事件循环"""
        while self.running:
            try:
                events = self.selector.poll(1000)  # 1秒超时
                
                for fd, event in events:
                    if fd == self.server_socket.fileno():
                        # 新连接
                        self._handle_new_connection()
                    else:
                        # 已有连接的消息
                        self._handle_client_message(fd)
                        
            except Exception as e:
                print(f"事件循环错误: {e}")
                if not self.running:
                    break
    
    def _handle_new_connection(self):
        """处理新连接"""
        try:
            client_socket, address = self.server_socket.accept()
            client_socket.setblocking(False)
            
            session = ClientSession(client_socket, address)
            self.sessions[client_socket] = session
            
            self.selector.register(client_socket, select.POLLIN)
            
            with self.lock:
                self.stats['connections'] += 1
            
            print(f"新客户端连接: {address}")
            
        except Exception as e:
            print(f"处理新连接时出错: {e}")
    
    def _handle_client_message(self, fd):
        """处理客户端消息"""
        client_socket = None
        for sock, session in self.sessions.items():
            if sock.fileno() == fd:
                client_socket = sock
                break
        
        if not client_socket:
            return
        
        session = self.sessions[client_socket]
        
        try:
            # 读取消息长度
            length_bytes = self._recv_all(client_socket, 4)
            if not length_bytes:
                self._disconnect_client(client_socket)
                return
            
            msg_length = struct.unpack('!I', length_bytes)[0]
            
            # 读取消息内容
            message_bytes = self._recv_all(client_socket, msg_length)
            if not message_bytes:
                self._disconnect_client(client_socket)
                return
            
            message_str = message_bytes.decode('utf-8')
            message = json.loads(message_str)
            
            with self.lock:
                self.stats['messages_received'] += 1
            
            # 处理消息
            self._process_client_message(session, message)
            
        except json.JSONDecodeError:
            print(f"无效的JSON消息来自 {session.address}")
            self._disconnect_client(client_socket)
        except Exception as e:
            print(f"处理客户端消息时出错: {e}")
            self._disconnect_client(client_socket)
    
    def _recv_all(self, sock: socket.socket, length: int) -> bytes:
        """接收指定长度的所有字节"""
        data = b''
        while len(data) < length:
            try:
                chunk = sock.recv(length - len(data))
                if not chunk:
                    return b''
                data += chunk
            except socket.error:
                return b''
        return data
    
    def _process_client_message(self, session: ClientSession, message: Dict):
        """处理客户端消息"""
        command = message.get('command')
        
        if command == 'subscribe':
            topic = message.get('topic')
            if topic:
                # 创建或获取主题
                topic_queue = self.router.create_topic(topic)
                # 订阅主题
                topic_queue.subscribe(lambda msg: self._forward_message_to_session(session, msg))
                session.add_subscription(topic)
                print(f"客户端 {session.address} 订阅了主题: {topic}")
                
                # 发送确认
                ack_msg = {'type': 'ack', 'command': 'subscribe', 'topic': topic}
                session.send_message(ack_msg)
        
        elif command == 'publish':
            topic = message.get('topic')
            payload = message.get('payload')
            if topic and payload:
                success = self.router.route_message(topic, payload)
                
                ack_msg = {
                    'type': 'ack', 
                    'command': 'publish', 
                    'topic': topic, 
                    'success': success
                }
                session.send_message(ack_msg)
                
                if success:
                    with self.lock:
                        self.stats['messages_sent'] += 1
        
        elif command == 'unsubscribe':
            topic = message.get('topic')
            if topic:
                session.remove_subscription(topic)
                ack_msg = {'type': 'ack', 'command': 'unsubscribe', 'topic': topic}
                session.send_message(ack_msg)
        
        elif command == 'stats':
            # 发送统计信息
            with self.lock:
                stats_copy = self.stats.copy()
            stats_copy['type'] = 'stats'
            session.send_message(stats_copy)
    
    def _forward_message_to_session(self, session: ClientSession, message: Dict):
        """转发消息到会话"""
        # 检查会话是否订阅了该消息的主题
        if message.get('__queue') in session.subscriptions:
            session.send_message(message)
    
    def _disconnect_client(self, client_socket: socket.socket):
        """断开客户端连接"""
        if client_socket in self.sessions:
            session = self.sessions[client_socket]
            print(f"客户端断开连接: {session.address}")
            
            # 从选择器中移除
            try:
                self.selector.unregister(client_socket)
            except KeyError:
                pass  # 可能已经被移除
            
            # 关闭套接字
            try:
                client_socket.close()
            except:
                pass
            
            # 从会话列表中移除
            del self.sessions[client_socket]
            
            with self.lock:
                self.stats['disconnections'] += 1
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self.lock:
            return self.stats.copy()


def main():
    """主函数演示"""
    broker = MessageBroker(host='localhost', port=9090)
    
    print("=== 实时消息代理演示 ===")
    print("功能:")
    print("- 支持多客户端连接")
    print("- 主题订阅/发布模式")
    print("- 消息持久化（内存中）")
    print("- 实时统计信息")
    print("")
    print("客户端协议:")
    print('{"command": "subscribe", "topic": "news"}')
    print('{"command": "publish", "topic": "news", "payload": {"title": "Hello"}}')
    print('{"command": "stats"}')
    print("")
    
    # 在单独线程中启动代理
    broker_thread = threading.Thread(target=broker.start, daemon=True)
    broker_thread.start()
    
    # 演示消息发布
    import time
    
    # 等待服务器启动
    time.sleep(1)
    
    print("启动测试生产者...")
    
    def test_publisher():
        """测试发布者"""
        time.sleep(2)  # 等待更多时间确保服务器完全启动
        
        # 创建发布者客户端
        pub_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            pub_sock.connect(('localhost', 9090))
            
            # 发布一些测试消息
            for i in range(5):
                message = {
                    'command': 'publish',
                    'topic': 'test-topic',
                    'payload': {
                        'id': i,
                        'message': f'Test message {i}',
                        'timestamp': datetime.now().isoformat()
                    }
                }
                
                msg_str = json.dumps(message)
                msg_bytes = msg_str.encode('utf-8')
                
                # 发送消息长度和内容
                pub_sock.send(struct.pack('!I', len(msg_bytes)))
                pub_sock.send(msg_bytes)
                
                print(f"发布消息 {i}")
                time.sleep(1)
            
            # 请求统计信息
            stats_msg = {'command': 'stats'}
            msg_str = json.dumps(stats_msg)
            msg_bytes = msg_str.encode('utf-8')
            pub_sock.send(struct.pack('!I', len(msg_bytes)))
            pub_sock.send(msg_bytes)
            
        except Exception as e:
            print(f"发布者错误: {e}")
        finally:
            pub_sock.close()
    
    publisher_thread = threading.Thread(target=test_publisher, daemon=True)
    publisher_thread.start()
    
    try:
        print("消息代理正在运行... 按 Ctrl+C 停止")
        while True:
            time.sleep(5)
            stats = broker.get_stats()
            print(f"统计: 连接数={stats['connections']}, "
                  f"消息接收={stats['messages_received']}, "
                  f"消息发送={stats['messages_sent']}")
    
    except KeyboardInterrupt:
        print("\n正在关闭消息代理...")
        broker.stop()


if __name__ == "__main__":
    main()