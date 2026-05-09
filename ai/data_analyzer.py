#!/usr/bin/env python3
"""
高级数据分析工具
使用Python标准库实现
"""
import csv
import json
import re
import statistics
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Union, Optional, Callable  # 添加Callable导入
import random
import threading
import time
import hashlib
import base64


class DataFrame:
    """简单的数据框实现"""
    
    def __init__(self, data: List[Dict[str, Any]] = None):
        if data is None:
            data = []
        self.data = data
        self.columns = list(data[0].keys()) if data else []
    
    def add_row(self, row: Dict[str, Any]):
        """添加一行数据"""
        if not self.columns:
            self.columns = list(row.keys())
        self.data.append(row)
    
    def filter(self, condition: Callable[[Dict[str, Any]], bool]) -> 'DataFrame':
        """过滤数据"""
        filtered_data = [row for row in self.data if condition(row)]
        return DataFrame(filtered_data)
    
    def select(self, columns: List[str]) -> 'DataFrame':
        """选择列"""
        selected_data = []
        for row in self.data:
            selected_row = {col: row.get(col) for col in columns if col in row}
            selected_data.append(selected_row)
        return DataFrame(selected_data)
    
    def group_by(self, column: str) -> Dict[Any, List[Dict[str, Any]]]:
        """按列分组"""
        groups = {}
        for row in self.data:
            key = row.get(column)
            if key not in groups:
                groups[key] = []
            groups[key].append(row)
        return groups
    
    def aggregate(self, agg_func: Dict[str, str]) -> 'DataFrame':
        """聚合操作"""
        # 简化版本，只处理基本聚合
        result = {}
        
        for col, func in agg_func.items():
            values = [row[col] for row in self.data if col in row and row[col] is not None]
            
            if not values:
                result[col] = None
                continue
            
            if func == 'sum':
                result[col] = sum(v for v in values if isinstance(v, (int, float)))
            elif func == 'mean':
                numeric_values = [v for v in values if isinstance(v, (int, float))]
                result[col] = sum(numeric_values) / len(numeric_values) if numeric_values else None
            elif func == 'count':
                result[col] = len(values)
            elif func == 'min':
                result[col] = min(v for v in values if isinstance(v, (int, float)))
            elif func == 'max':
                result[col] = max(v for v in values if isinstance(v, (int, float)))
            elif func == 'std':
                numeric_values = [v for v in values if isinstance(v, (int, float))]
                if len(numeric_values) > 1:
                    result[col] = statistics.stdev(numeric_values)
                else:
                    result[col] = 0
        
        return DataFrame([result])
    
    def sort(self, column: str, ascending: bool = True) -> 'DataFrame':
        """排序"""
        sorted_data = sorted(
            self.data,
            key=lambda x: x.get(column, 0),
            reverse=not ascending
        )
        return DataFrame(sorted_data)
    
    def head(self, n: int = 5) -> 'DataFrame':
        """获取前n行"""
        return DataFrame(self.data[:n])
    
    def tail(self, n: int = 5) -> 'DataFrame':
        """获取后n行"""
        return DataFrame(self.data[-n:])
    
    def describe(self) -> 'DataFrame':
        """数据描述统计"""
        if not self.data or not self.columns:
            return DataFrame()
        
        stats = {}
        for col in self.columns:
            values = [row[col] for row in self.data if col in row and row[col] is not None]
            
            if not values:
                continue
            
            # 尝试转换为数值型进行统计
            numeric_values = []
            for val in values:
                if isinstance(val, (int, float)):
                    numeric_values.append(val)
                elif isinstance(val, str):
                    try:
                        numeric_values.append(float(val))
                    except ValueError:
                        pass
            
            if numeric_values:
                stats[col] = {
                    'count': len(numeric_values),
                    'mean': sum(numeric_values) / len(numeric_values),
                    'std': statistics.stdev(numeric_values) if len(numeric_values) > 1 else 0,
                    'min': min(numeric_values),
                    'max': max(numeric_values),
                    'q25': sorted(numeric_values)[int(len(numeric_values)*0.25)],
                    'q50': sorted(numeric_values)[int(len(numeric_values)*0.50)],
                    'q75': sorted(numeric_values)[int(len(numeric_values)*0.75)]
                }
            else:
                stats[col] = {
                    'count': len(values),
                    'unique': len(set(str(v) for v in values)),
                    'top': max(set(values), key=values.count) if values else None,
                    'freq': values.count(max(set(values), key=values.count)) if values else 0
                }
        
        # 转换为DataFrame格式
        max_len = max(len(v) for v in stats.values()) if stats else 0
        result_data = []
        
        for stat_type in ['count', 'mean', 'std', 'min', 'max', 'q25', 'q50', 'q75']:
            row = {'statistic': stat_type}
            for col, col_stats in stats.items():
                if stat_type in col_stats:
                    row[col] = col_stats[stat_type]
            result_data.append(row)
        
        return DataFrame(result_data)
    
    def to_csv(self, filename: str):
        """导出为CSV"""
        if not self.data:
            return
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = self.columns
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.data:
                writer.writerow(row)
    
    def to_json(self, filename: str):
        """导出为JSON"""
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(self.data, jsonfile, ensure_ascii=False, indent=2)


class DataAnalyzer:
    """高级数据分析器"""
    
    def __init__(self):
        self.datasets = {}
        self.analyses = {}
    
    def load_csv(self, filename: str, name: str = None) -> DataFrame:
        """加载CSV文件"""
        if name is None:
            name = filename
        
        data = []
        with open(filename, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # 尝试转换数值型数据
                processed_row = {}
                for key, value in row.items():
                    # 尝试转换为数字
                    if value.replace('.', '').replace('-', '').isdigit():
                        processed_row[key] = float(value) if '.' in value else int(value)
                    # 尝试转换为布尔值
                    elif value.lower() in ['true', 'false']:
                        processed_row[key] = value.lower() == 'true'
                    # 保持原样
                    else:
                        processed_row[key] = value
                data.append(processed_row)
        
        df = DataFrame(data)
        self.datasets[name] = df
        return df
    
    def load_json(self, filename: str, name: str = None) -> DataFrame:
        """加载JSON文件"""
        if name is None:
            name = filename
        
        with open(filename, 'r', encoding='utf-8') as jsonfile:
            data = json.load(jsonfile)
        
        df = DataFrame(data)
        self.datasets[name] = df
        return df
    
    def generate_sample_data(self, rows: int = 100) -> DataFrame:
        """生成示例数据"""
        data = []
        
        for i in range(rows):
            row = {
                'id': i + 1,
                'name': f'User_{random.randint(1000, 9999)}',
                'age': random.randint(18, 80),
                'salary': round(random.uniform(30000, 150000), 2),
                'department': random.choice(['Engineering', 'Sales', 'Marketing', 'HR']),
                'experience': random.randint(0, 20),
                'performance_score': round(random.uniform(1.0, 5.0), 2),
                'join_date': (datetime.now() - timedelta(days=random.randint(0, 365*5))).strftime('%Y-%m-%d'),
                'is_active': random.choice([True, False])
            }
            data.append(row)
        
        df = DataFrame(data)
        self.datasets['sample_data'] = df
        return df
    
    def correlation_matrix(self, df: DataFrame, columns: List[str] = None) -> Dict[str, Dict[str, float]]:
        """计算相关矩阵"""
        if columns is None:
            # 选择数值列
            columns = []
            if df.data:
                for col in df.columns:
                    if all(isinstance(row.get(col), (int, float)) for row in df.data if row.get(col) is not None):
                        columns.append(col)
        
        result = {}
        for col1 in columns:
            result[col1] = {}
            for col2 in columns:
                values1 = [row[col1] for row in df.data if col1 in row and isinstance(row[col1], (int, float))]
                values2 = [row[col2] for row in df.data if col2 in row and isinstance(row[col2], (int, float))]
                
                # 确保两个列表长度相同
                min_len = min(len(values1), len(values2))
                values1 = values1[:min_len]
                values2 = values2[:min_len]
                
                if len(values1) > 1:
                    # 计算皮尔逊相关系数
                    mean1 = sum(values1) / len(values1)
                    mean2 = sum(values2) / len(values2)
                    
                    numerator = sum((x - mean1) * (y - mean2) for x, y in zip(values1, values2))
                    sum_sq_x = sum((x - mean1) ** 2 for x in values1)
                    sum_sq_y = sum((y - mean2) ** 2 for y in values2)
                    
                    denominator = math.sqrt(sum_sq_x * sum_sq_y)
                    
                    if denominator != 0:
                        corr = numerator / denominator
                        result[col1][col2] = round(corr, 4)
                    else:
                        result[col1][col2] = 0.0
                else:
                    result[col1][col2] = 0.0
        
        return result
    
    def regression_analysis(self, df: DataFrame, dependent_col: str, independent_cols: List[str]) -> Dict[str, Any]:
        """执行回归分析"""
        # 准备数据
        y_vals = [row[dependent_col] for row in df.data 
                  if dependent_col in row and isinstance(row[dependent_col], (int, float))]
        
        x_vals = []
        for col in independent_cols:
            col_vals = [row[col] for row in df.data 
                       if col in row and isinstance(row[col], (int, float))]
            x_vals.append(col_vals)
        
        # 确保所有列表长度相同
        min_len = min(len(y_vals), *[len(x_col) for x_col in x_vals])
        y_vals = y_vals[:min_len]
        x_vals = [x_col[:min_len] for x_col in x_vals]
        
        # 简化的多元线性回归实现
        # Y = b0 + b1*X1 + b2*X2 + ... + bn*Xn
        # 使用最小二乘法的简化版本
        
        # 计算均值
        y_mean = sum(y_vals) / len(y_vals)
        x_means = [sum(x_col) / len(x_col) for x_col in x_vals]
        
        # 计算回归系数
        coefficients = []
        for i, x_col in enumerate(x_vals):
            numerator = sum((x - x_means[i]) * (y - y_mean) for x, y in zip(x_col, y_vals))
            denominator = sum((x - x_means[i])**2 for x in x_col)
            
            if denominator != 0:
                coeff = numerator / denominator
                coefficients.append(coeff)
            else:
                coefficients.append(0.0)
        
        # 计算截距
        intercept = y_mean - sum(coeff * x_mean for coeff, x_mean in zip(coefficients, x_means))
        
        # 计算预测值和R²
        predicted_vals = []
        for i in range(len(y_vals)):
            pred_val = intercept
            for j, x_col in enumerate(x_vals):
                pred_val += coefficients[j] * x_col[i]
            predicted_vals.append(pred_val)
        
        # 计算R²
        ss_res = sum((actual - predicted)**2 for actual, predicted in zip(y_vals, predicted_vals))
        ss_tot = sum((actual - y_mean)**2 for actual in y_vals)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        
        return {
            'intercept': intercept,
            'coefficients': dict(zip(independent_cols, coefficients)),
            'r_squared': r_squared,
            'predicted_values': predicted_vals,
            'actual_values': y_vals
        }
    
    def generate_report(self, df: DataFrame, title: str = "Analysis Report") -> str:
        """生成分析报告"""
        report = []
        report.append(f"# {title}")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        report.append(f"Dataset shape: {len(df.data)} rows × {len(df.columns)} columns")
        report.append("")
        
        # 基本统计
        desc_df = df.describe()
        report.append("## Basic Statistics")
        for row in desc_df.data:
            stat = row.get('statistic', '')
            if stat:
                report.append(f"- {stat}:")
                for col in [c for c in df.columns if c != 'statistic']:
                    if col in row and row[col] is not None:
                        report.append(f"  - {col}: {row[col]}")
                report.append("")
        
        # 相关性分析（如果有数值列）
        numeric_cols = []
        if df.data:
            for col in df.columns:
                if all(isinstance(row.get(col), (int, float)) for row in df.data if row.get(col) is not None):
                    numeric_cols.append(col)
        
        if len(numeric_cols) >= 2:
            report.append("## Correlation Analysis")
            corr_matrix = self.correlation_matrix(df, numeric_cols[:5])  # 限制列数以便显示
            for col1, corrs in list(corr_matrix.items())[:5]:
                report.append(f"- {col1}:")
                for col2, corr in list(corrs.items())[:5]:
                    report.append(f"  - {col2}: {corr}")
            report.append("")
        
        return "\n".join(report)


def main():
    """主函数演示"""
    analyzer = DataAnalyzer()
    
    print("=== 高级数据分析工具演示 ===")
    
    # 生成示例数据
    df = analyzer.generate_sample_data(50)
    print(f"生成了 {len(df.data)} 行示例数据")
    
    # 显示前几行
    print("\n前5行数据:")
    for row in df.head().data:
        print(f"  {row}")
    
    # 基本统计
    print("\n基本统计:")
    desc_df = df.describe()
    for row in desc_df.data:
        if row.get('statistic') in ['count', 'mean', 'std', 'min', 'max']:
            print(f"  {row}")
    
    # 过滤数据
    high_salary_df = df.filter(lambda row: row.get('salary', 0) > 80000)
    print(f"\n高薪员工数量: {len(high_salary_df.data)}")
    
    # 分组统计
    grouped = df.group_by('department')
    print("\n各部门人数:")
    for dept, employees in grouped.items():
        print(f"  {dept}: {len(employees)} 人")
    
    # 相关性分析
    print("\n薪资与经验的相关性:")
    corr_matrix = analyzer.correlation_matrix(df, ['salary', 'experience'])
    print(f"  Salary vs Experience: {corr_matrix['salary']['experience']}")
    
    # 回归分析
    print("\n回归分析 (Performance Score ~ Salary + Experience):")
    try:
        reg_result = analyzer.regression_analysis(
            df, 
            dependent_col='performance_score', 
            independent_cols=['salary', 'experience']
        )
        print(f"  R²: {reg_result['r_squared']:.4f}")
        print(f"  截距: {reg_result['intercept']:.4f}")
        for var, coeff in reg_result['coefficients'].items():
            print(f"  {var} 系数: {coeff:.4f}")
    except Exception as e:
        print(f"  回归分析失败: {e}")
    
    # 生成报告
    report = analyzer.generate_report(df, "Sample Employee Data Analysis")
    print(f"\n生成报告预览 (前100字符):")
    print(report[:100] + "..." if len(report) > 100 else report)


if __name__ == "__main__":
    main()