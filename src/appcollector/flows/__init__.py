from appcollector.flows.feed_random_walk import FeedRandomWalk
from appcollector.flows.generic_random_walk import GenericRandomWalk
from appcollector.flows.news_browse import NewsBrowse
from appcollector.flows.passive_media import PassiveMedia
from appcollector.flows.shopping_browse import ShoppingBrowse

FLOW_REGISTRY = {
    "feed_random_walk": FeedRandomWalk,
    "passive_media": PassiveMedia,
    "news_browse": NewsBrowse,
    "shopping_browse": ShoppingBrowse,
    "generic_random_walk": GenericRandomWalk,
}
