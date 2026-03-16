# BaoYanMessage

**项目简介**  

BaoYanMessage网站是为了汇总展示各高校的保研（推免）和夏令营信息，包括截止日期、报名条件和年份等。  
网站提供搜索、筛选和高亮显示即将到截止日期的功能，让用户快速查看目标高校信息。

> 当前网站已经在本地构建完成，域名未来将申请，会提供在线访问地址。  
> Die aktuelle Website wurde bereits lokal erstellt, der Domainname wird in Zukunft beantragt, und es wird eine Online-Zugriffsadresse bereitgestellt.

---

## 功能
- 高校保研与夏令营信息展示
- 支持按学校名搜索
- 支持按年份和类型（保研/夏令营）筛选
- 高亮即将到截止日期的条目
- 点击标题可跳转至原官网链接

---

## 安装与运行

### 1. 克隆仓库 

```bash
git clone https://github.com/YOUR_USERNAME/SchoolDDLHub.git
cd SchoolDDLHub
```

### 2.创建虚拟环境（可选）

```bash
python -m venv .venv
# Linux/Mac
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```
### 3.修改MySql密码

### 4.安装依赖

pip install -r backend/requirements.txt

### 5.运行后端

python backend/app.py

### 6.打开浏览器访问


## 数据

数据存储在 MySQL 或 JSON 文件中

## 贡献

欢迎贡献数据或优化前端页面

可提交 Pull Request 或 Issues
