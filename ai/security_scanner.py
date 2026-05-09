#!/usr/bin/env python3
"""
网络安全扫描器
使用Python标准库实现
"""
import socket
import threading
import time
import ssl
import urllib.request
import urllib.parse
from datetime import datetime
import hashlib
import re
from typing import List, Dict, Optional, Tuple
import json


class PortScanner:
    """端口扫描器"""
    
    def __init__(self, timeout: float = 1.0):
        self.timeout = timeout
    
    def scan_port(self, host: str, port: int) -> bool:
        """扫描单个端口"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except socket.gaierror:
            return False
        except Exception:
            return False
    
    def scan_ports(self, host: str, ports: List[int], max_threads: int = 100) -> Dict[int, bool]:
        """并发扫描多个端口"""
        results = {}
        threads = []
        semaphore = threading.Semaphore(max_threads)
        
        def scan_worker(port):
            with semaphore:
                results[port] = self.scan_port(host, port)
        
        for port in ports:
            thread = threading.Thread(target=scan_worker, args=(port,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        return results


class VulnerabilityDetector:
    """漏洞检测器"""
    
    def __init__(self):
        # 常见漏洞特征模式
        self.vulnerability_patterns = {
            'sql_injection': [
                r"(\bUNION\b.*\bSELECT\b)|(\bSELECT\b.*\bFROM\b.*\bWHERE\b)|('\bOR\b'|'\bAND\b')",
                r"(?i)(\bEXEC\b|\bEXECUTE\b|\bDECLARE\b|\bDROP\b|\bCREATE\b|\bALTER\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b)"
            ],
            'xss': [
                r"<script[^>]*>.*?</script>",
                r"(?i)(javascript:|on\w+\s*=)",
                r"<iframe[^>]*>.*?</iframe>"
            ],
            'path_traversal': [
                r"\.\./", r"\.\.\\",
                r"%2e%2e%2f", r"%2e%2e%5c"
            ]
        }
    
    def check_vulnerabilities(self, content: str) -> Dict[str, List[str]]:
        """检查内容中的漏洞"""
        findings = {}
        
        for vuln_type, patterns in self.vulnerability_patterns.items():
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                matches.extend(found)
            
            if matches:
                findings[vuln_type] = matches
        
        return findings


class SecurityScanner:
    """综合安全扫描器"""
    
    def __init__(self, max_threads: int = 50):
        self.port_scanner = PortScanner()
        self.vuln_detector = VulnerabilityDetector()
        self.max_threads = max_threads
        self.scan_history = []
    
    def scan_website(self, url: str, check_common_ports: bool = True) -> Dict[str, any]:
        """扫描网站安全状况"""
        start_time = time.time()
        
        parsed_url = urllib.parse.urlparse(url)
        host = parsed_url.hostname
        port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
        
        result = {
            'url': url,
            'host': host,
            'port': port,
            'scan_timestamp': datetime.now().isoformat(),
            'open_ports': [],
            'vulnerabilities': {},
            'ssl_info': {},
            'headers': {},
            'scan_duration': 0
        }
        
        # 扫描常见端口
        if check_common_ports:
            common_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 993, 995, 3306, 3389, 5432, 6379]
            port_results = self.port_scanner.scan_ports(host, common_ports, self.max_threads)
            result['open_ports'] = [port for port, is_open in port_results.items() if is_open]
        
        # 获取网页内容并检查漏洞
        try:
            request = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'SecurityScanner/1.0',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
            )
            response = urllib.request.urlopen(request, timeout=10)
            
            content = response.read().decode('utf-8', errors='ignore')
            headers = dict(response.headers)
            
            result['headers'] = headers
            result['content_length'] = len(content)
            
            # 检查漏洞
            vulnerabilities = self.vuln_detector.check_vulnerabilities(content)
            result['vulnerabilities'] = vulnerabilities
            
        except Exception as e:
            result['error'] = str(e)
        
        # 检查SSL证书（如果是HTTPS）
        if parsed_url.scheme == 'https':
            try:
                context = ssl.create_default_context()
                with socket.create_connection((host, 443), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        cert = ssock.getpeercert()
                        result['ssl_info'] = {
                            'subject': dict(x[0] for x in cert['subject']),
                            'issuer': dict(x[0] for x in cert['issuer']),
                            'version': cert['version'],
                            'serial_number': cert['serialNumber'],
                            'not_before': cert['notBefore'],
                            'not_after': cert['notAfter']
                        }
            except Exception as e:
                result['ssl_error'] = str(e)
        
        result['scan_duration'] = round(time.time() - start_time, 2)
        self.scan_history.append(result)
        
        return result
    
    def scan_multiple_sites(self, urls: List[str]) -> List[Dict[str, any]]:
        """扫描多个网站"""
        results = []
        threads = []
        semaphore = threading.Semaphore(self.max_threads)
        
        def scan_worker(url):
            with semaphore:
                result = self.scan_website(url)
                results.append(result)
        
        for url in urls:
            thread = threading.Thread(target=scan_worker, args=(url,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # 按时间排序
        results.sort(key=lambda x: x['scan_timestamp'], reverse=True)
        return results
    
    def generate_security_report(self, results: List[Dict]) -> str:
        """生成安全扫描报告"""
        report = []
        report.append("# 安全扫描报告")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"扫描网站数量: {len(results)}")
        report.append("")
        
        high_risk_count = 0
        medium_risk_count = 0
        
        for result in results:
            report.append(f"## 网站: {result['url']}")
            report.append(f"- 扫描时间: {result['scan_timestamp']}")
            report.append(f"- 扫描耗时: {result['scan_duration']}秒")
            
            if 'open_ports' in result:
                report.append(f"- 开放端口: {', '.join(map(str, result['open_ports']))}")
            
            if 'vulnerabilities' in result and result['vulnerabilities']:
                report.append("- 检测到漏洞:")
                for vuln_type, matches in result['vulnerabilities'].items():
                    severity = "高风险" if vuln_type in ['sql_injection', 'path_traversal'] else "中风险"
                    report.append(f"  - {vuln_type} ({severity}): {len(matches)} 个匹配项")
                    
                    if vuln_type in ['sql_injection', 'path_traversal']:
                        high_risk_count += len(matches)
                    else:
                        medium_risk_count += len(matches)
            else:
                report.append("- 未检测到明显漏洞")
            
            if 'ssl_info' in result:
                report.append("- SSL证书信息:")
                ssl_info = result['ssl_info']
                report.append(f"  - 颁发者: {ssl_info.get('issuer', {}).get('organizationName', 'N/A')}")
                report.append(f"  - 过期时间: {ssl_info.get('not_after', 'N/A')}")
            
            report.append("")
        
        report.append("## 总体风险评估")
        report.append(f"- 高风险漏洞: {high_risk_count} 个")
        report.append(f"- 中风险漏洞: {medium_risk_count} 个")
        
        if high_risk_count > 0:
            report.append("- 风险等级: 高危")
            report.append("- 建议: 立即修复高风险漏洞")
        elif medium_risk_count > 0:
            report.append("- 风险等级: 中危")
            report.append("- 建议: 尽快修复中风险漏洞")
        else:
            report.append("- 风险等级: 低危")
            report.append("- 建议: 继续监控")
        
        return "\n".join(report)


def main():
    """主函数演示"""
    scanner = SecurityScanner(max_threads=20)
    
    print("=== 网络安全扫描器演示 ===")
    
    # 示例网站列表（使用测试网站）
    test_urls = [
        "https://httpbin.org/",
        "https://example.com/"
    ]
    
    print(f"开始扫描 {len(test_urls)} 个网站...")
    results = scanner.scan_multiple_sites(test_urls)
    
    # 显示结果摘要
    for result in results:
        print(f"\n网站: {result['url']}")
        print(f"  开放端口: {result['open_ports']}")
        print(f"  漏洞数量: {len(result.get('vulnerabilities', []))}")
        print(f"  扫描耗时: {result['scan_duration']}秒")
    
    # 生成详细报告
    report = scanner.generate_security_report(results)
    print(f"\n=== 安全报告预览 ===")
    print(report[:500] + "..." if len(report) > 500 else report)
    
    # 保存报告到文件
    with open("security_scan_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("\n详细报告已保存到 security_scan_report.md")


if __name__ == "__main__":
    main()