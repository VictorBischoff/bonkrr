"""Scrapy integration for the bunkrr package."""
from .processor import MediaProcessor
from .pipelines import MediaPipeline, DownloadPipeline
from .middlewares import RateLimitMiddleware
from .spiders.bunkr_spider import BunkrSpider

__all__ = [
    'MediaProcessor',
    'MediaPipeline',
    'DownloadPipeline',
    'RateLimitMiddleware',
    'BunkrSpider'
]
