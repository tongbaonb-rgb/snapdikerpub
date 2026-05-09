#!/usr/bin/env python3
"""
高级网络爬虫框架
使用Python标准库实现
"""
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
import time
import random
import threading
import queue
import re
import json
import ssl
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.robotparser import RobotFileParser
from typing import List, Dict, Optional, Callable, Any
import socket
import hashlib


class RateLimiter:
    """速率限制器"""
    
    def __init__(self, requests_per_second: float = 1.0):
        self.requests_per_second = requests_per_second
        self.interval = 1.0 / requests_per_second
        self.last_request_time = 0
        self.lock = threading.Lock()
    
    def wait(self):
        """等待直到可以发送下一个请求"""
        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            
            if time_since_last < self.interval:
                sleep_time = self.interval - time_since_last
                time.sleep(sleep_time)
            
            self.last_request_time = time.time()


class RobotsChecker:
    """robots.txt检查器"""
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=1)
    
    def can_fetch(self, url: str, user_agent: str = '*') -> bool:
        """检查是否允许抓取指定URL"""
        parsed_url = urllib.parse.urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # 检查缓存
        cache_key = f"{base_url}_robots"
        if cache_key in self.cache:
            cached_time, rp = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return rp.can_fetch(user_agent, url)
        
        # 从网络获取robots.txt
        try:
            rp = RobotFileParser()
            robots_url = f"{base_url}/robots.txt"
            rp.set_url(robots_url)
            rp.read()
            
            # 缓存结果
            self.cache[cache_key] = (datetime.now(), rp)
            return rp.can_fetch(user_agent, url)
        except:
            # 如果无法获取robots.txt，默认允许
            return True


class ContentExtractor(HTMLParser):
    """内容提取器"""
    
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
        self.title = ""
        self.in_title = False
        self.links = []
        self.meta_description = ""
        self.in_meta = False
        self.meta_attrs = {}
    
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag.lower() == 'title':
            self.in_title = True
        elif tag.lower() == 'a' and 'href' in attrs_dict:
            self.links.append(attrs_dict['href'])
        elif tag.lower() == 'meta':
            self.in_meta = True
            self.meta_attrs = attrs_dict
    
    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.in_title = False
        elif tag.lower() == 'meta':
            self.in_meta = False
            if self.meta_attrs.get('name', '').lower() == 'description':
                self.meta_description = self.meta_attrs.get('content', '')
            self.meta_attrs = {}
    
    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.in_meta:
            self.fed.append(data)
    
    def get_data(self):
        return ''.join(self.fed).strip()


class PageCrawler:
    """页面爬取器"""
    
    def __init__(self, 
                 user_agent: str = "AdvancedBot/1.0",
                 delay_range: tuple = (1, 3),
                 timeout: int = 30,
                 max_retries: int = 3):
        
        self.user_agent = user_agent
        self.delay_range = delay_range
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 设置Cookie处理器
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        
        # 设置SSL上下文
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        self.rate_limiter = RateLimiter(requests_per_second=1.0/delay_range[1])
        self.robots_checker = RobotsChecker()
    
    def fetch_page(self, url: str) -> Optional[Dict[str, Any]]:
        """获取页面内容"""
        # 检查robots.txt
        if not self.robots_checker.can_fetch(url, self.user_agent):
            print(f"Robots.txt禁止访问: {url}")
            return None
        
        # 应用速率限制
        self.rate_limiter.wait()
        
        for attempt in range(self.max_retries):
            try:
                # 构建请求
                headers = {
                    'User-Agent': self.user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
                
                req = urllib.request.Request(url, headers=headers)
                
                # 发起请求
                with self.opener.open(req, timeout=self.timeout, context=self.ssl_context) as response:
                    content_type = response.headers.get('Content-Type', '')
                    
                    if 'text/html' not in content_type.lower():
                        print(f"跳过非HTML内容: {url}")
                        return None
                    
                    html_content = response.read().decode('utf-8', errors='ignore')
                    
                    # 解析内容
                    extractor = ContentExtractor()
                    extractor.feed(html_content)
                    
                    return {
                        'url': url,
                        'status_code': response.getcode(),
                        'headers': dict(response.headers),
                        'title': extractor.title.strip() or "No Title",
                        'content': extractor.get_data()[:2000],  # 限制内容长度
                        'meta_description': extractor.meta_description,
                        'links': extractor.links,
                        'content_type': content_type,
                        'timestamp': datetime.now().isoformat()
                    }
                    
            except urllib.error.HTTPError as e:
                print(f"HTTP错误 {e.code} 获取 {url} (尝试 {attempt + 1}/{self.max_retries})")
                if e.code in [404, 410]:  # 永久性错误，不再重试
                    break
            except urllib.error.URLError as e:
                print(f"URL错误获取 {url}: {e.reason} (尝试 {attempt + 1}/{self.max_retries})")
            except socket.timeout:
                print(f"请求超时获取 {url} (尝试 {attempt + 1}/{self.max_retries})")
            except Exception as e:
                print(f"未知错误获取 {url}: {str(e)} (尝试 {attempt + 1}/{self.max_retries})")
            
            if attempt < self.max_retries - 1:
                # 指数退避
                backoff_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(backoff_time)
        
        return None


class CrawlerScheduler:
    """爬虫调度器"""
    
    def __init__(self, 
                 max_workers: int = 5,
                 max_depth: int = 3,
                 domain_limit: int = 100):
        
        self.max_workers = max_workers
        self.max_depth = max_depth
        self.domain_limit = domain_limit
        
        self.url_queue = queue.Queue()
        self.visited_urls = set()
        self.visited_domains = {}
        self.results = []
        self.lock = threading.Lock()
        
        # 启动工作线程
        self.workers = []
        for _ in range(max_workers):
            worker = threading.Thread(target=self.worker_thread, daemon=True)
            worker.start()
            self.workers.append(worker)
    
    def add_url(self, url: str, depth: int = 0):
        """添加URL到队列"""
        with self.lock:
            if url not in self.visited_urls and depth <= self.max_depth:
                self.url_queue.put((url, depth))
    
    def worker_thread(self):
        """工作线程函数"""
        crawler = PageCrawler()
        
        while True:
            try:
                url, depth = self.url_queue.get(timeout=10)
                
                with self.lock:
                    if url in self.visited_urls:
                        self.url_queue.task_done()
                        continue
                    self.visited_urls.add(url)
                
                print(f"正在爬取 (深度 {depth}): {url}")
                
                result = crawler.fetch_page(url)
                
                if result:
                    with self.lock:
                        self.results.append(result)
                        
                        # 检查域名限制
                        domain = urllib.parse.urlparse(url).netloc
                        if domain not in self.visited_domains:
                            self.visited_domains[domain] = 0
                        self.visited_domains[domain] += 1
                        
                        # 添加新的链接到队列（如果未超过深度和域名限制）
                        if depth < self.max_depth:
                            for link in result['links']:
                                absolute_url = urllib.parse.urljoin(url, link)
                                link_domain = urllib.parse.urlparse(absolute_url).netloc
                                
                                if (absolute_url not in self.visited_urls and 
                                    self.visited_domains.get(link_domain, 0) < self.domain_limit):
                                    self.url_queue.put((absolute_url, depth + 1))
                
                self.url_queue.task_done()
                
            except queue.Empty:
                break
            except Exception as e:
                print(f"工作线程错误: {str(e)}")
                self.url_queue.task_done()
    
    def crawl(self, start_urls: List[str]) -> List[Dict[str, Any]]:
        """开始爬取"""
        print(f"开始爬取 {len(start_urls)} 个起始URL...")
        
        # 添加起始URL
        for url in start_urls:
            self.add_url(url)
        
        # 等待所有任务完成
        self.url_queue.join()
        
        print(f"爬取完成！共获取 {len(self.results)} 个页面")
        return self.results


def main():
    """主函数演示"""
    scheduler = CrawlerScheduler(max_workers=3, max_depth=2, domain_limit=5)
    
    # 示例起始URL（请替换为实际URL）
    start_urls = [
        "https://httpbin.org/html"
    ]
    
    results = scheduler.crawl(start_urls)
    
    print("\n=== 爬取结果摘要 ===")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title'][:50]}...")
        print(f"   URL: {result['url']}")
        print(f"   状态: {result['status_code']}")
        print(f"   内容长度: {len(result['content'])}")
        print(f"   链接数量: {len(result['links'])}")
        print()


if __name__ == "__main__":
    main()