#  Copyright (C) 2023 Yesh
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as
#  published by the Free Software Foundation, either version 3 of the
#  License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os.path
import re
import time
import typing
from urllib.parse import urlparse

import qbittorrentapi

import byre.clients
from byre import utils
from byre.clients.data import LocalTorrent, TorrentInfo, TypedTorrent
from byre.commands.config import GlobalConfig

_logger = logging.getLogger("byre.bt")
_debug, _info, _warning, _fatal = (
    _logger.debug,
    _logger.info,
    _logger.warning,
    _logger.fatal,
)


class BtClient:
    """对 qBittorrent 客户端的各种操作进行封装。"""

    def __init__(self, url: str) -> None:
        info = urlparse(url)
        scheme = info.scheme or "http"
        #: qBittorrent 连接。
        self.client = qbittorrentapi.Client(
            host=f"{scheme}://{info.hostname}",
            port=info.port,
            username=info.username,
            password=info.password,
        )
        self.client.auth_log_in()
        _debug(
            "qBittorrent 信息：软件版本 %s，API 版本 %s",
            self.client.app.version,
            self.client.app.web_api_version,
        )
        if self.client.app.version < "v4.5.2":
            raise ConnectionError("请升级到更新的 qBittorrent 版本")
        #: 一些额外的配置（可通过 load_config 覆写）
        self.upload_limit = 95.0

    def load_config(self, config: GlobalConfig):
        self.upload_limit = config.optional(
            float, 95.0, "qbittorrent", "upload_speed_limit"
        )

    def init_webui(self, username: str, password: str):
        """设置 Web UI 的用户名和密码。"""
        self.client.app_set_preferences(
            {
                "web_ui_username": username,
                "web_ui_password": password,
            }
        )

    def init_categories(
        self, download_dir: str, categories: typing.Iterable[str]
    ) -> None:
        """创建类别并设置下载目录，不会更改现有类别的设置。"""
        existing = set(self.client.torrents_categories().keys())
        for category in categories:
            if category in existing:
                _debug("类别“%s”已存在，跳过创建", category)
                continue
            download_dir = os.path.join(os.path.realpath(download_dir), category)
            _debug("正在创建类别“%s”", category)
            self.client.torrents_create_category(
                category,
                torrent_dir=download_dir,
            )

    def remove_categories(self, categories: typing.Iterable[str]) -> None:
        """删除类别。"""
        existing = set(self.client.torrents_categories().keys())
        removable = existing & set(categories)
        _debug("计划删除类别 %s，最终应删除 %s", categories, removable)
        self.client.torrents_remove_categories(removable)

    def init_tags(self, reset=False) -> None:
        """创建（或删除）“byr”和“keep”标签。"""
        tags = self.client.torrents_tags()
        for tag in [*byre.clients.SITES.keys(), "keep"]:
            if tag not in tags:
                if not reset:
                    self.client.torrents_create_tags([tag])
                    _debug("创建了“%s”标签", tag)
                    continue
            elif reset:
                self.client.torrents_delete_tags([tag])
                _debug("删除了“%s”标签", tag)
                continue
            _debug("无需创建/删除“%s”", tag)

    def add_torrent(
        self,
        torrent: bytes,
        info: TorrentInfo,
        download_dir: str,
        paused: bool = False,
        exists: typing.Union[bool, LocalTorrent] = False,
    ) -> None:
        """添加种子并设置对应的类别和标签。"""
        title = self._generate_rename(info)
        _info("正在添加种子“%s”", title)
        if isinstance(exists, LocalTorrent):
            save_path = exists.torrent.save_path
            _info("将种子设定保存路径设为 %s 并取消哈希检查", save_path)
        else:
            save_path = self._get_download_dir(download_dir, info)
        self.client.torrents_add(
            torrent_files=torrent,
            save_path=save_path,
            category=info.category,
            is_skip_checking=bool(exists),
            is_paused=paused,
            rename=title,
            tags=[info.site],
            upload_limit=int(self.upload_limit * 1024 * 1024),
        )

    def rename_torrent(self, torrent: LocalTorrent, info: TorrentInfo) -> None:
        """重新按照格式命名种子。"""
        title = self._generate_rename(info)
        self.client.torrents_rename(torrent.torrent.hash, title)

    def remove_torrent(
        self,
        torrent: LocalTorrent,
        extra: typing.Optional[typing.Iterable[LocalTorrent]] = None,
    ) -> None:
        """
        删除种子并删除对应的文件。

        - ``extra`` : 是共用文件的其它应同步删除的种子，会先删除这些种子（但不删除文件），
          然后再删除 ``torrent`` 并删除所有下载文件。
        """
        if extra is not None:
            _info(
                "正在删除共用文件种子：\n%s", "\n".join(t.torrent.name for t in extra)
            )
            self.client.torrents_delete(
                delete_files=False, torrent_hashes=(t.torrent.hash for t in extra)
            )
            time.sleep(0.5)
        _info("正在删除种子“%s”", torrent.torrent.name)
        self.client.torrents_delete(
            delete_files=True, torrent_hashes=[torrent.torrent.hash]
        )

    def list_torrents(
        self,
        remote_torrents: list[TorrentInfo],
        wants_all=False,
        site: typing.Optional[str] = None,
    ) -> list[LocalTorrent]:
        """列出所有本地带有对应 NexusPHP 标签且命名符合要求的种子。"""
        if site is None:
            gathered = []
            for site in byre.clients.SITES.keys():
                gathered.extend(
                    self.list_torrents(remote_torrents, wants_all=wants_all, site=site)
                )
            return gathered
        remote_mapping = dict((t.seed_id, t) for t in remote_torrents if t.site == site)
        torrents = []
        for torrent in self.client.torrents_info(tag=site):
            try:
                local = self.local_torrent_from(torrent, site)
                local.info = remote_mapping.get(local.seed_id, None)
                torrents.append(local)
            except ValueError as e:
                _warning(e)
                if wants_all:
                    torrents.append(LocalTorrent(TypedTorrent(torrent), 0, site, None))
        return torrents

    @classmethod
    def local_torrent_from(
        cls,
        torrent: qbittorrentapi.TorrentDictionary,
        site: typing.Optional[str] = None,
    ):
        t = TypedTorrent(torrent)
        name = t.name
        if site is None:
            match = re.match("^\\[(\\w+)-\\d+]", name)
            if match is None:
                raise ValueError(f"种子命名不符合要求：{name}")
            site = match.group(1)
        prefix = f"[{site}-"
        if name.startswith(prefix):
            seed_id = utils.int_or(name[len(prefix) : name.index("]")])
            if seed_id != 0:
                return LocalTorrent(t, seed_id, utils.cast(str, site), None)
        raise ValueError(f"种子命名不符合要求：{name}")

    @classmethod
    def _get_download_dir(cls, download_dir: str, torrent: TorrentInfo) -> str:
        """下载目录，由种子分类及二级分类决定。"""
        realpath = os.path.realpath(download_dir)
        return (
            os.path.join(realpath, torrent.category, torrent.second_category)
            if torrent.second_category
            else os.path.join(realpath, torrent.category)
        )

    @staticmethod
    def _generate_rename(info: TorrentInfo) -> str:
        return f"[{info.site}-{info.seed_id}]{info.title}"
