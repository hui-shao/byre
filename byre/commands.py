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

import typing

import click
import tabulate
import tomli

from byre import ByrApi, BtClient, ByrClient, TorrentPromotion, TorrentInfo, ByrSortableField


class GlobalConfig(click.ParamType):
    """配置信息以及各种命令。"""

    name = "配置文件路径"

    config: dict[str, typing.Any] = None

    byr_credentials = ("", "", "")

    qbittorrent_url = ""

    download_dir = ""

    size_limit = ""

    free_weight = 0.

    cost_recovery_days = 0.

    removal_exemption_days = 0.

    byr: ByrApi = None
    bt: BtClient = None

    def convert(self, value: str, param, ctx):
        with open(value, "rb") as file:
            self.config = tomli.load(file)

        self.byr_credentials = (
            self._require(str, "byr", "username"),
            self._require(str, "byr", "password"),
            self._optional(str, "byr.cookies", "byr", "cookie_cache")
        )
        self.qbittorrent_url, self.download_dir, self.size_limit = (
            self._require(str, "qbittorrent", "url"),
            self._require(str, "qbittorrent", "download_dir"),
            self._require(float, "qbittorrent", "size_limit"),
        )
        self.free_weight = self._optional(float, 1., "scoring", "free_weight")
        self.cost_recovery_days = self._optional(float, 7., "scoring", "cost_recovery_days")
        self.removal_exemption_days = self._optional(float, 15., "scoring", "removal_exemption_days")
        return self

    def init(self, byr=False, bt=False):
        """初始化北邮人客户端等。"""
        if byr:
            self.byr = ByrApi(ByrClient(*self.byr_credentials))
        if bt:
            self.bt = BtClient(self.qbittorrent_url, self.download_dir)

    def display_torrent_info(self, seed: str):
        if seed.isdigit():
            seed_id = int(seed)
        else:
            seed_id = ByrApi.extract_url_id(seed)
        self.init(byr=True)
        torrent = self.byr.torrent(seed_id)
        click.echo(tabulate.tabulate([
            ("标题", click.style(torrent.title, bold=True)),
            ("副标题", click.style(torrent.sub_title, dim=True)),
            ("链接", click.style(f"https://byr.pt/details.php?id={torrent.seed_id}", underline=True)),
            ("类型", click.style(f"{torrent.cat} - {torrent.second_category}", fg="bright_red")),
            ("促销", click.style(str(torrent.promotions), fg="bright_yellow")),
            ("大小", click.style(f"{torrent.file_size:.2f} GB", fg="cyan")),
            ("存活时间", click.style(f"{torrent.live_time:.2f} 天", fg="bright_green")),
            ("做种人数", f"~ {torrent.seeders}"),
            ("下载人数", click.style(f"~ {torrent.leechers}", fg="bright_magenta")),
            ("上传用户", f"{torrent.uploader.username} " +
             (click.style(f"<https://byr.pt/userdetails.php?id={torrent.uploader.user_id}>", underline=True)
              if torrent.uploader.user_id != 0 else "")
             ),
        ], maxcolwidths=[2, 10, 70], showindex=True))

    def display_user_info(self, user_id=0):
        self.init(byr=True)
        user = self.byr.user_info(user_id)
        if user.user_id != self.byr.current_user_id():
            click.echo("查询的用户并非当前登录用户，限于权限，信息可能不准确")
        click.echo(tabulate.tabulate([
            ("用户名", click.style(user.username, bold=True)),
            ("链接", click.style(f"https://byr.pt/details.php?id={user.user_id}", underline=True)),
            ("等级", click.style(user.level, fg="bright_yellow")),
            ("魔力值", click.style(f"{user.mana}", fg="bright_magenta")),
            ("可连接", click.style("是", fg="bright_green") if user.connectable else click.style("否", dim=True)),
            ("下载量", click.style(f"{user.downloaded:.2f} GB", fg="yellow")),
            ("上传量", click.style(f"{user.uploaded:.2f} GB", fg="bright_blue")),
            ("分享率", click.style(f"{user.ratio:.2f}", fg="cyan")),
            ("当前活动", f"{user.seeding}↑ {user.downloading}↓"),
            ("上传排行", click.style(f"{user.ranking}", dim=True)),
        ], showindex=True))

    def list_torrents(self, page=0, promotions=TorrentPromotion.ANY, sorted_by=ByrSortableField.ID):
        self.init(byr=True)
        torrents = self.byr.list_torrents(page, promotion=promotions, sorted_by=sorted_by)
        self._display_torrents(torrents)

    def _require(self, typer: typing.Callable, *args):
        config = self.config
        for arg in args:
            if arg not in config:
                raise ValueError(f"缺失 {'.'.join(args)} 配置参数")
            config = config[arg]
        try:
            return typer(config)
        except ValueError as e:
            raise ValueError(f"配置项 {'.'.join(args)} 的值 {config} 无效：{e}")

    def _optional(self, typer: typing.Callable, default: typing.Any, *args):
        try:
            return self._require(typer, *args)
        except ValueError:
            return default

    @staticmethod
    def _display_torrents(torrents: list[TorrentInfo]):
        table = []
        header = ["ID", "标题", "大小", "时间"]
        limits = [8, 60, 10, 10]
        for t in torrents:
            table.append((
                t.seed_id,
                click.style(t.title, bold=True),
                click.style(f"{t.file_size:.2f} GB", fg="bright_yellow"),
                click.style(f"{t.live_time:.2f} 天", fg="bright_magenta"),
            ))
            table.append((
                "",
                click.style(t.sub_title, dim=True)
                + "(" + click.style(f"{t.seeders}↑", fg="bright_green")
                + " " + click.style(f"{t.leechers}↓", fg="cyan") + " )",
                "",
                "",
            ))
        click.echo_via_pager(tabulate.tabulate(table, headers=header, maxcolwidths=limits))