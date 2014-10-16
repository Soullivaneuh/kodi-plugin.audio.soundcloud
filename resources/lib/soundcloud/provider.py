from functools import partial
import re
from resources.lib.kodimon.helper import FunctionCache
from resources.lib.kodimon import DirectoryItem, AudioItem, constants, KodimonException
from resources.lib import kodimon

__author__ = 'bromix'


class Provider(kodimon.AbstractProvider):
    def __init__(self, plugin=None):
        kodimon.AbstractProvider.__init__(self, plugin)

        self.set_localization({'soundcloud.explore': 30500,
                               'soundcloud.music.trending': 30501,
                               'soundcloud.audio.trending': 30502,
                               'soundcloud.music.genre': 30503,
                               'soundcloud.audio.genre': 30504,
                               'soundcloud.stream': 30505,
                               'soundcloud.playlists': 30506, })

        from resources.lib import soundcloud

        if self.has_login_credentials():
            username, password = self.get_login_credentials()
            access_token = self.get_access_token()

            self._client = soundcloud.Client(username=username, password=password, access_token=access_token)

            # create a new access_token
            if self.is_new_login_credential():
                access_token = self._client.update_access_token()
                self.update_access_token(access_token)
                pass
        else:
            self._client = soundcloud.Client()
        pass

    def get_fanart(self):
        """
        This will return a darker and (with blur) fanart
        :return:
        """
        return self.create_resource_path('media', 'fanart.jpg')

    def _get_hires_image(self, url):
        return re.sub('(.*)(-large.jpg\.*)(\?.*)?', r'\1-t500x500.jpg', url)

    def _get_track_year(self, collection_item_json):
        # this would be the default info, but is mostly not set :(
        year = collection_item_json.get('release_year', '')
        if year:
            return year

        # we use a fallback.
        # created_at=2013/03/24 00:32:01 +0000
        re_match = re.match('(?P<year>\d{4})(.*)', collection_item_json.get('created_at', ''))
        if re_match:
            year = re_match.group('year')
            if year:
                return year
            pass

        return ''

    @kodimon.RegisterPath('^/play/$')
    def _play(self, path, params, re_match):
        track_id = params.get('id', '')
        if not track_id:
            raise kodimon.KodimonException('Missing if for audio file')

        json_data = self._client.get_track_url(track_id)
        location = json_data.get('location')
        if not location:
            raise kodimon.KodimonException("Could not get url for trask '%s'" % track_id)

        item = kodimon.AudioItem(track_id, location)
        return item

    def _do_collection(self, json_data, path, params):

        self.set_content_type(constants.CONTENT_TYPE_SONGS)

        """
        Helper function to display the items of a collection
        :param json_data:
        :param path:
        :param params:
        :return:
        """
        result = []

        collection = json_data.get('collection', [])
        for item in collection:
            kind = item.get('kind', '')
            if kind == 'user':
                image = self._get_hires_image(item['avatar_url'])
                user_item = DirectoryItem('[B]' + item['username'] + '[/B]',
                                          self.create_uri(['user', str(item['id'])]),
                                          image=image)
                user_item.set_fanart(self.get_fanart())
                result.append(user_item)
            elif kind == 'track':
                # some tracks don't provide an artwork so we do it like soundcloud and return the avatar of the user
                image = item.get('artwork_url', '')
                if not image:
                    image = item.get('user', {}).get('avatar_url', '')
                    pass
                if image:
                    image = self._get_hires_image(image)
                    pass

                title = item['title']
                audio_item = AudioItem(title,
                                       self.create_uri('play', {'id': unicode(item['id'])}),
                                       image=image)
                audio_item.set_fanart(self.get_fanart())

                # title
                audio_item.set_title(title)

                # genre
                audio_item.set_genre(item.get('genre', ''))

                # duration
                audio_item.set_duration_in_milli_seconds(item.get('duration', 0))

                # artist
                audio_item.set_artist_name(item.get('user', {}).get('username', ''))

                # year
                audio_item.set_year(self._get_track_year(item))

                result.append(audio_item)
                pass
            pass

        # test for next page
        next_href = json_data.get('next_href', '')
        page = int(params.get('page', 1))
        if next_href and len(collection) > 0:
            next_page_item = self.create_next_page_item(page,
                                                        path,
                                                        params)
            result.append(next_page_item)
            pass

        return result

    def _do_mobile_collection(self, json_data, path, params):
        result = []

        collection = json_data.get('collection', [])
        for item in collection:
            # some tracks don't provide an artwork so we do it like soundcloud and return the avatar of the user
            image = item.get('artwork_url', '')
            if not image:
                image = item.get('_embedded', {}).get('user', {}).get('avatar_url', '')
                pass
            if image:
                image = self._get_hires_image(image)
                pass

            title = item['title']
            track_id = item['urn'].split(':')[2]
            audio_item = AudioItem(title,
                                   self.create_uri('play', {'id': track_id}),
                                   image=image)
            audio_item.set_fanart(self.get_fanart())

            # title
            audio_item.set_title(title)

            # genre
            audio_item.set_genre(item.get('genre', ''))

            # duration
            audio_item.set_duration_in_milli_seconds(item.get('duration', 0))

            # artist
            audio_item.set_artist_name(item.get('_embedded', {}).get('user', {}).get('username', ''))

            # year
            audio_item.set_year(self._get_track_year(item))

            result.append(audio_item)
            pass

        # test for next page
        page = int(params.get('page', 1))
        next_href = json_data.get('_links', {}).get('next', {}).get('href', '')
        if next_href and len(result) > 0:
            next_page_item = self.create_next_page_item(page,
                                                        path,
                                                        params)
            result.append(next_page_item)
            pass

        return result

    @kodimon.RegisterPath('^\/explore\/trending\/((?P<category>\w+)/)?$')
    def _on_explore_trending(self, path, params, re_match):
        result = []
        category = re_match.group('category')
        page = int(params.get('page', 1))
        json_data = self.call_function_cached(partial(self._client.get_trending, category=category, page=page),
                                              seconds=FunctionCache.ONE_HOUR)
        result = self._do_mobile_collection(json_data, path, params)

        return result

    @kodimon.RegisterPath('^\/explore\/genre\/((?P<category>\w+)\/)((?P<genre>.+)\/)?$')
    def _on_explore_genre(self, path, params, re_match):
        result = []

        genre = re_match.group('genre')
        if not genre:
            json_data = self.call_function_cached(partial(self._client.get_categories), seconds=FunctionCache.ONE_DAY)
            category = re_match.group('category')
            genres = json_data.get(category, [])
            for genre in genres:
                title = genre['title']
                genre_item = DirectoryItem(title,
                                           self.create_uri(['explore', 'genre', category, title]))
                genre_item.set_fanart(self.get_fanart())
                result.append(genre_item)
                pass
        else:
            page = int(params.get('page', 1))
            json_data = self.call_function_cached(partial(self._client.get_genre, genre=genre, page=page),
                                                  seconds=FunctionCache.ONE_HOUR)
            result = self._do_mobile_collection(json_data, path, params)
            pass

        return result

    @kodimon.RegisterPath('^\/explore\/?$')
    def _on_explore(self, path, params, re_match):
        result = []

        # trending music
        music_trending_item = DirectoryItem(self.localize('soundcloud.music.trending'),
                                            self.create_uri(['explore', 'trending', 'music']))
        music_trending_item.set_fanart(self.get_fanart())
        result.append(music_trending_item)

        # trending audio
        audio_trending_item = DirectoryItem(self.localize('soundcloud.audio.trending'),
                                            self.create_uri(['explore', 'trending', 'audio']))
        audio_trending_item.set_fanart(self.get_fanart())
        result.append(audio_trending_item)

        # genre music
        music_genre_item = DirectoryItem(self.localize('soundcloud.music.genre'),
                                         self.create_uri(['explore', 'genre', 'music']))
        music_genre_item.set_fanart(self.get_fanart())
        result.append(music_genre_item)

        # genre audio
        audio_genre_item = DirectoryItem(self.localize('soundcloud.audio.genre'),
                                         self.create_uri(['explore', 'genre', 'audio']))
        audio_genre_item.set_fanart(self.get_fanart())
        result.append(audio_genre_item)

        return result

    @kodimon.RegisterPath('^\/playlists\/(?P<user_id>.+)/$')
    def _on_playlists(self, path, params, re_match):
        result = []

        user_id = re_match.group('user_id')
        json_data = self._client.get_playlists(user_id)
        for json_item in json_data:
            result.append(self._json_item_to_item(json_item))
            pass

        return result

    @kodimon.RegisterPath('^\/stream\/$')
    def _on_stream(self, path, params, re_match):
        result = []

        json_data = self._client.get_stream()
        collection = json_data.get('collection', [])
        for collection_item in collection:
            item_type = collection_item.get('type', '')
            if item_type == 'track':
                item = collection_item['track']
                # some tracks don't provide an artwork so we do it like soundcloud and return the avatar of the user
                image = item.get('artwork_url', '')
                if not image:
                    image = item.get('user', {}).get('avatar_url', '')
                    pass
                if image:
                    image = self._get_hires_image(image)
                    pass

                title = item['title']
                audio_item = AudioItem(title,
                                       self.create_uri('play', {'id': unicode(item['id'])}),
                                       image=image)
                audio_item.set_fanart(self.get_fanart())

                # title
                audio_item.set_title(title)

                # genre
                audio_item.set_genre(item.get('genre', ''))

                # duration
                audio_item.set_duration_in_milli_seconds(item.get('duration', 0))

                # artist
                audio_item.set_artist_name(item.get('user', {}).get('username', ''))

                # year
                audio_item.set_year(self._get_track_year(item))

                result.append(audio_item)
                pass
            pass

        # next page works with an cursor?!?!?!?
        # next_href=https://api.soundcloud.com/e1/me/stream?cursor=6e011980-48af-11e4-80d9-f79411997475&limit=100

        return result

    def on_search(self, search_text, path, params, re_match):
        page = params.get('page', 1)
        json_data = self.call_function_cached(partial(self._client.search, search_text, page=page),
                                              seconds=FunctionCache.ONE_MINUTE)
        return self._do_collection(json_data, path, params)

    def on_root(self, path, params, re_match):
        result = []

        # search
        search_item = DirectoryItem(self.localize(self.LOCAL_SEARCH),
                                    self.create_uri([self.PATH_SEARCH, 'list']),
                                    image=self.create_resource_path('media', 'search.png'))
        search_item.set_fanart(self.get_fanart())
        result.append(search_item)

        # is logged in?
        is_logged_in = self._is_logged_in()

        # stream
        if is_logged_in:
            stream_item = DirectoryItem(self.localize('soundcloud.stream'),
                                        self.create_uri(['stream']))
            stream_item.set_fanart(self.get_fanart())
            result.append(stream_item)
            pass

        # explore
        explore_item = DirectoryItem(self.localize('soundcloud.explore'),
                                     self.create_uri('explore'))
        explore_item.set_fanart(self.get_fanart())
        result.append(explore_item)

        # playlists
        if is_logged_in:
            playlists_item = DirectoryItem(self.localize('soundcloud.playlists'),
                                           self.create_uri('playlists/me'))
            playlists_item.set_fanart(self.get_fanart())
            result.append(playlists_item)
            pass

        return result

    def _is_logged_in(self):
        access_token = self.get_access_token()
        access_token_client = self._client.get_access_token()

        return access_token != '' and access_token_client != '' and access_token == access_token_client

    def _json_item_to_item(self, json_item):
        def _get_image(json_data):
            image_url = json_data.get('artwork_url', '')

            # test tracks (used for playlists)
            if not image_url:
                tracks = json_data.get('tracks', [])
                if len(tracks) > 0:
                    return _get_image(tracks[0])

                # fall back is the user avatar (at least)
                image_url = json_data.get('user', {}).get('avatar_url', '')
                pass

            # try to convert the image to 500x500 pixel
            return self._get_hires_image(image_url)

        kind = json_item.get('kind', '')
        if kind == 'playlist':
            playlist_item = DirectoryItem(json_item['title'],
                                          '',
                                          image=_get_image(json_item))
            playlist_item.set_fanart(self.get_fanart())
            return playlist_item

        raise KodimonException("Unknown kind of item '%s'" % kind)

    pass
