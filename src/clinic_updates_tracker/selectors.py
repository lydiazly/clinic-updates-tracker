# -*- coding: utf-8 -*-
# src/clinic_updates_tracker/selectors.py

TITLE_SELECTOR = 'h2:has-text("Family Clinics in")'
UPDATES_CONTAINER_SELECTOR = f'div.elementor-widget-container:has({TITLE_SELECTOR})'
UPDATES_TITLE_SELECTOR = 'strong:has-text("Updates regarding")'  # UPDATES_CONTAINER_SELECTOR >
UPDATES_LIST_SELECTOR = 'ul'  # UPDATES_CONTAINER_SELECTOR >
UPDATES_ITEM_SELECTOR = 'li'  # UPDATES_LIST_SELECTOR >
UPDATES_EMPTY_SELECTOR = 'p:has-text("There is no recent news")'  # UPDATES_CONTAINER_SELECTOR >

