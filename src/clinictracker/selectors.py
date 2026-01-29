# -*- coding: utf-8 -*-
# selectors.py


TITLE_PREFIX = "Family Clinics in"
LIST_TITLE_PREFIX = "Updates regarding"
EMPTY_SIGN_PREFIX = "There is no recent news"


# Home page, landing page, or the result page
class HomePageSelectors:
    TITLE = f'h2:has-text("{TITLE_PREFIX}")'
    CONTAINER = 'div.elementor-widget-container:has(' + TITLE + ')'
    LIST_TITLE = f'strong:has-text("{LIST_TITLE_PREFIX}")'  # CONTAINER >
    EMPTY_SIGN = f'p:has-text("{EMPTY_SIGN_PREFIX}")'  # CONTAINER >
    CITY_LIST = 'select[name="list_town"]'


# Detail page of an item
class DetailPageSelectors:
    TITLE = 'div.elementor-page-title h4.elementor-heading-title'
    # DATE = 'ul.elementor-post-info > li[itemprop="datePublished"] time'
    DATE_PARENT = 'ul.elementor-post-info > li[itemprop="datePublished"]'
    CONTENT = (
        'div.elementor-widget-theme-post-content > '
        'div.elementor-widget-container'
    )
