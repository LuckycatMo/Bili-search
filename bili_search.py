# from spider_util import *
import re
import pandas as pd
from loguru import logger
import random
import math
import time
import streamlit as st
import requests
from requests import Response,Request
from datetime import datetime,timezone
import json

import subprocess

# 劫持 subprocess，强行指定编码为 utf-8，修复 Windows 终端下的 GBK 冲突
_original_Popen = subprocess.Popen

class UTF8Popen(_original_Popen):
    def __init__(self, *args, **kwargs):
        if kwargs.get('text') is True or kwargs.get('universal_newlines') is True:
            if 'encoding' not in kwargs:
                kwargs['encoding'] = 'utf-8'
        super().__init__(*args, **kwargs)

subprocess.Popen = UTF8Popen

import execjs
log_format = ("<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
              "<level>{level:<8}</level> | "
              "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>")

BASEURL= "https://search.bilibili.com/video"

def normal_headers(cookies=None):
    '''
    user-agent
    '''
    if cookies:
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/111.0.1661.44',
            'cookie':cookies
        }
    else:
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/111.0.1661.44'
        }
    return headers

def to_hex_ceil(num):
    """向上取整并转为大写十六进制（去掉0x）"""
    return hex(math.ceil(num))[2:].upper()

def random_hex_string(length):
    """生成长度为length的随机十六进制串（可能含两位字符），并补零至至少length位"""
    result = ""
    for _ in range(length):
        result += to_hex_ceil(16 * random.random())
    return result.zfill(length)

def generate_b_lsid(millisecond):
    """
    生成与JavaScript中一致的b_lsid值
    :param millisecond: 数字，通常是时间戳毫秒值
    :return: 字符串格式：8位随机十六进制 + '_' + millisecond的十六进制
    """
    return random_hex_string(8) + '_' + to_hex_ceil(millisecond)

def constrct_params(query,page):
    if page!=1:
        params = {
        "vt": 35783245,
        "keyword": query,          # 可直接写中文，requests会自行编码
        "from_source": "webtop_search",
        "spm_id_from": "333.1007",
        "search_source": 3,
        "page": page,
        "o": page*24
    }
    else:
        params = {
        "keyword": query,          # 可直接写中文，requests会自行编码
        "from_source": "webtop_search",
        "spm_id_from": "333.1007",
        "search_source": 3,
        }
        
    return params

def modify_cookie(raw_cookies:str):
    cookie = raw_cookies[0:-20]+generate_b_lsid(int(time.time() * 1000))
    return cookie

def parser(res:Response):
    match=re.search(r'window\.__pinia\s*=\s*(.*?)</script>', res.text, re.S).group(1)
    info_dict=execjs.eval(match)
    res_list=info_dict['searchTypeResponse']['searchTypeResponse']['result']
    return res_list

def get_fans_mid(mid,cookies):
    card_url='https://api.bilibili.com/x/web-interface/card'
    param_card={
        'mid':mid,
        'photo':1
    }
    cookie=modify_cookie(raw_cookies=cookies)
    res=requests.get(card_url,params=param_card,headers=normal_headers(cookies=cookie))
    return res.json()['data']['card']['fans']

def get_details_url(url,cookies):
    cookie=modify_cookie(raw_cookies=cookies)
    try:
        res=requests.get(url,headers=normal_headers(cookies=cookie))
        assert res.status_code==200
    except:
        logger.error(f'视频详细信息访问失败:{url}')
    match=re.search(r'window\.__INITIAL_STATE__\s*=\s*(.*?);', res.text, re.S)

    return json.loads(match.group(1))['videoData']['stat']

st.set_page_config(page_title="B站抓取工具", layout="wide")
st.title("📺 Bilibili 视频采集 (Execjs版)")

with st.sidebar:
    st.warning("⚠️ 注意：此版本依赖 Node.js 环境，如果电脑没装 Node.js 可能会运行缓慢或报错。")
    cookies = st.text_area("输入 Cookie (必填)", height=150)
    query = st.text_input("关键词")
    pages = st.number_input("页数", 1, 50, 1)

if st.button("开始抓取", type="primary"):
    if not cookies or not query:
        st.error("请完善信息")
    else:
        st.info("开始运行...")
        res_list = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            for page in range(pages):
                status_text.text(f"正在抓取第 {page+1} 页...")
                res = requests.get(BASEURL, 
                                 params=constrct_params(query, page), 
                                 headers=normal_headers(cookies))
                
                res_list = res_list + parser(res)
                st.success(f"第 {page+1} 页解析成功")
                progress_bar.progress((page + 1) / (pages + 1))
                time.sleep(1)

            # 获取详情
            if res_list:
                status_text.text("正在补充详情数据...")
                for i, item in enumerate(res_list):
                    try:
                        item['fans'] = get_fans_mid(item['mid'], cookies)
                        details = get_details_url(item['arcurl'], cookies)
                        if details: item.update(details)
                    except: pass
                    
                    if i % 5 == 0:
                        progress_bar.progress(0.9) # 简单展示进度
                
                progress_bar.progress(1.0)
                df = pd.DataFrame(res_list)
                st.dataframe(df)
                
                # 下载按钮
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button("下载CSV", df.to_csv(index=False).encode('utf-8-sig'), f"result_{timestamp}.csv")
            else:
                st.error("未获取到数据")

        except Exception as e:
            st.error(f"发生错误: {str(e)}")