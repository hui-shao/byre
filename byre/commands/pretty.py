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

import time

import click
import tabulate

from byre.clients import CLIENTS
from byre.clients.api import NexusApi
from byre.clients.data import TorrentInfo, NexusUser, LocalTorrent
from byre.utils import S


def parse_url_id(s: str):
    """把用户输入里抑或是链接抑或是 ID 的字符串转为 ID。"""
    if s.isdigit():
        return int(s)
    else:
        return NexusApi.extract_url_id(s)


def pretty_torrent_info(torrent: TorrentInfo):
    click.echo(
        tabulate.tabulate(
            [
                ("标题", click.style(torrent.title, bold=True)),
                ("副标题", click.style(torrent.sub_title, dim=True)),
                (
                    "链接",
                    click.style(
                        CLIENTS[torrent.site].get_url(
                            f"details.php?id={torrent.seed_id}"
                        ),
                        underline=True,
                    ),
                ),
                (
                    "类型",
                    click.style(
                        f"{torrent.cat} - {torrent.second_category}", fg="bright_red"
                    ),
                ),
                ("促销", click.style(str(torrent.promotions), fg="bright_yellow")),
                ("大小", click.style(f"{S(torrent.file_size)}", fg="cyan")),
                (
                    "存活时间",
                    click.style(f"{torrent.live_time:.2f} 天", fg="bright_green"),
                ),
                ("做种人数", f"{torrent.seeders}"),
                ("下载人数", click.style(f"{torrent.leechers}", fg="bright_magenta")),
                (
                    "上传用户",
                    f"{torrent.uploader.username} "
                    + (
                        click.style(
                            f'<{CLIENTS[torrent.site].get_url(f"userdetails.php?id={torrent.uploader.user_id}")}>',
                            underline=True,
                        )
                        if torrent.uploader.user_id != 0
                        else ""
                    ),
                ),
            ],
            maxcolwidths=[2, 10, 60],
            showindex=True,
            disable_numparse=True,
        )
    )


def pretty_user_info(user: NexusUser):
    click.echo(
        tabulate.tabulate(
            [
                ("用户名", click.style(user.username, bold=True)),
                (
                    "链接",
                    click.style(
                        CLIENTS[user.site].get_url(f"details.php?id={user.user_id}"),
                        underline=True,
                    ),
                ),
                ("等级", click.style(user.level, fg="bright_yellow")),
                ("魔力值", click.style(f"{user.mana}", fg="bright_magenta")),
                (
                    "可连接",
                    (
                        click.style("是", fg="bright_green")
                        if user.connectable
                        else click.style("否", dim=True)
                    ),
                ),
                ("下载量", click.style(f"{S(user.downloaded)}", fg="yellow")),
                ("上传量", click.style(f"{S(user.uploaded)}", fg="bright_blue")),
                ("分享率", click.style(f"{user.ratio:.2f}", fg="cyan")),
                ("当前活动", f"{user.seeding}↑ {user.downloading}↓"),
                ("上传排行", click.style(f"{user.ranking}", dim=True)),
            ],
            showindex=True,
            disable_numparse=True,
        )
    )


def pretty_torrent_list(torrents: list[TorrentInfo]):
    if len(torrents) == 0:
        click.echo("种子列表为空")
        return
    table = []
    header = ["ID", "标题", ""]
    limits = [8, 54, 10]
    for t in torrents:
        promotion = (
            ""
            if len(list(t.promotions.get_promotions())) == 0
            else click.style(f"[{str(t.promotions)}] ", fg="bright_yellow")
        )
        table.append(
            (
                t.seed_id,
                click.style(t.title, bold=True),
                click.style(f"{S(t.file_size)}", fg="bright_yellow"),
            )
        )
        table.append(
            (
                "",
                promotion
                + click.style(t.sub_title, dim=True)
                + " ("
                + click.style(f"{t.seeders}↑", fg="bright_green")
                + " "
                + click.style(f"{t.leechers}↓", fg="cyan")
                + " )",
                click.style(f"{t.live_time:.2f} 天", fg="bright_magenta"),
            )
        )
    click.echo_via_pager(
        tabulate.tabulate(
            table, headers=header, maxcolwidths=limits, disable_numparse=True
        )
    )


def pretty_local_torrents(torrents: list[LocalTorrent], speed=False):
    if len(torrents) == 0:
        click.echo("种子列表为空")
        return
    table = []
    header = ["最后活跃", "标题", "速度" if speed else "累计", "分享率"]
    limits = [8, 44, 10, 10]
    for t in torrents:
        days = (time.time() - t.torrent.last_activity) / (24 * 60 * 60)
        table.append(
            (
                click.style(f"{days:.2f} 天", fg="yellow"),
                click.style(t.torrent.name, bold=True),
                click.style(
                    (
                        f"{S(t.torrent.upspeed)}/s↑"
                        if speed
                        else f"{S(t.torrent.uploaded)}↑"
                    ),
                    fg="bright_green",
                ),
                click.style(f"{t.torrent.ratio:.2f}", fg="bright_yellow"),
            )
        )
        table.append(
            (
                click.style(t.site, fg="bright_cyan"),
                click.style(t.torrent.hash, dim=True)
                + " ("
                + click.style(f"{t.torrent.num_complete}↑", fg="bright_green")
                + " "
                + click.style(f"{t.torrent.num_incomplete}↓", fg="cyan")
                + " )",
                click.style(
                    (
                        f"{S(t.torrent.dlspeed)}/s↓"
                        if speed
                        else f"{S(t.torrent.downloaded)}↓"
                    ),
                    fg="cyan",
                ),
                click.style(f"/ {S(t.torrent.size)}", dim=True),
            )
        )
    click.echo_via_pager(
        tabulate.tabulate(
            table, headers=header, maxcolwidths=limits, disable_numparse=True
        )
    )


def pretty_rename(pending: list[LocalTorrent]) -> str:
    if len(pending) == 0:
        return "种子列表为空"
    failed, found = [], []
    arrow = click.style("=>", dim=True)
    for t in pending:
        if t.seed_id == 0:
            failed.append(
                (
                    click.style("!!", fg="bright_red"),
                    click.style(t.torrent.name, fg="bright_red"),
                    f"{S(t.torrent.size)}",
                    t.torrent.hash[:7],
                )
            )
            failed.append(
                (
                    arrow,
                    click.style("未能找到匹配", fg="yellow"),
                    "",
                    "",
                )
            )
        else:
            found.append(
                (
                    click.style("✓", fg="bright_green"),
                    click.style(t.torrent.name, fg="cyan"),
                    f"{S(t.torrent.size)}",
                    t.torrent.hash[:7],
                )
            )
            info = t.estimate_info()
            found.append(
                (
                    arrow,
                    click.style(info.title, fg="bright_green"),
                    f"{S(info.file_size)}",
                    info.hash[:7],
                )
            )
    return tabulate.tabulate(
        (*failed, *found), maxcolwidths=[2, 50, 10, 10], disable_numparse=True
    )


def pretty_changes(
    removable: list[LocalTorrent],
    downloadable: list[TorrentInfo],
    duplicates: dict[str, list[LocalTorrent]],
) -> str:
    if len(removable) == 0 and len(downloadable) == 0:
        return "无变更"
    all_removable = []
    for t in removable:
        all_removable.append(
            (
                click.style("删", fg="bright_red"),
                click.style(f"{t.seed_id}", dim=True),
                click.style(t.torrent.name, dim=True),
                click.style(f"-{S(t.torrent.size)}", fg="bright_green"),
                "",
            )
        )
        for dup in duplicates[t.torrent.hash]:
            all_removable.append(
                (
                    click.style("同", fg="bright_yellow"),
                    click.style(f"{dup.seed_id}", dim=True),
                    click.style(dup.torrent.name, dim=True),
                    click.style(dup.site, fg="yellow"),
                    "",
                )
            )
    return tabulate.tabulate(
        (
            *all_removable,
            *(
                (
                    click.style("新", fg="bright_cyan"),
                    click.style(f"{t.seed_id}", dim=True),
                    click.style(t.title, bold=True),
                    click.style(f"+{S(t.file_size)}", fg="yellow"),
                    click.style(str(t.promotions), fg="yellow"),
                )
                for t in downloadable
            ),
        ),
        maxcolwidths=[2, 8, 42, 10, 10],
        disable_numparse=True,
    )


def pretty_scored_torrents(torrents: list[tuple[TorrentInfo, float]]):
    if len(torrents) == 0:
        click.echo("种子列表为空")
        return
    table = []
    header = ["评分", "标题", ""]
    limits = [8, 54, 10]
    for t, score in torrents:
        table.append(
            (
                click.style(f"{score:.2f}", fg="bright_yellow"),
                click.style(t.title, bold=True),
                click.style(f"{S(t.file_size)}", fg="yellow"),
            )
        )
        table.append(
            (
                "",
                click.style(t.sub_title, dim=True)
                + " ("
                + click.style(f"{t.seeders}↑", fg="bright_green")
                + " "
                + click.style(f"{t.leechers}↓", fg="cyan")
                + " "
                + click.style(f"{t.finished}✓", fg="yellow")
                + " )",
                click.style(f"{t.live_time:.2f} 天", fg="bright_magenta"),
            )
        )
    click.echo_via_pager(
        tabulate.tabulate(
            table, headers=header, maxcolwidths=limits, disable_numparse=True
        )
    )


def pretty_comparison(
    local: LocalTorrent,
    torrent: TorrentInfo,
    local_files: dict[str, int],
    remote_files: dict[str, int],
):
    r_arrow = click.style("==>", fg="bright_green")
    l_arrow = click.style("<==", fg="bright_yellow")
    table = [
        (r_arrow, local.torrent.name, f"{S(local.torrent.size)}"),
        (l_arrow, torrent.title, f"{S(torrent.file_size)}"),
    ]
    for filename, size in local_files.items():
        table.append((r_arrow, filename, f"{S(size)}"))
        table.append((l_arrow, filename, f"{S(remote_files[filename])}"))
    click.echo_via_pager(
        tabulate.tabulate(table, maxcolwidths=[3, 60, 10], disable_numparse=True)
    )
