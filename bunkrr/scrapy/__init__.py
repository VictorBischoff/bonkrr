"""Scrapy integration for the bunkrr package."""
from .processor import MediaProcessor
from .pipelines import BunkrFilesPipeline, BunkrDownloadPipeline
from .middlewares import CustomRateLimiterMiddleware
from .spiders.bunkr_spider import BunkrSpider

__all__ = [
    'MediaProcessor',
    'BunkrFilesPipeline',
    'BunkrDownloadPipeline',
    'CustomRateLimiterMiddleware',
    'BunkrSpider'
]
