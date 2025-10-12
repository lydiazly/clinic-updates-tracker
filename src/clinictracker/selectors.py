# -*- coding: utf-8 -*-
# selectors.py


# Home page, landing page, or the result page
class HomePageSelectors:
    TITLE = 'h2:has-text("Family Clinics in")'
    CONTAINER = 'div.elementor-widget-container:has(' + TITLE + ')'
    LIST_TITLE = 'strong:has-text("Updates regarding")'  # CONTAINER >
    LIST = 'ul'  # CONTAINER >
    ITEM = 'li'  # LIST >
    EMPTY_CUE = 'p:has-text("There is no recent news")'  # CONTAINER >


# Detail page of an item
class DetailPageSelectors:
    TITLE = 'div.elementor-page-title h4.elementor-heading-title'
    DATE = (
        'ul.elementor-post-info > '
        'li[itemprop="datePublished"] time'
    )
    CONTENT = (
        'div.elementor-widget-theme-post-content > '
        'div.elementor-widget-container'
    )
