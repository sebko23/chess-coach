"use no memo";
import { AppShellSection, Stack, Tooltip } from "@mantine/core";
import {
  type Icon,
  IconBrain,
  IconChess,
  IconCpu,
  IconDatabase,
  IconFiles, IconList,
  IconBinaryTree,
  IconBooks,
  IconCloudDownload, IconSettings,
  IconTarget,
  IconUser,
} from "@tabler/icons-react";
import { Link, useMatchRoute } from "@tanstack/react-router";
import cx from "clsx";
import { useTranslation } from "react-i18next";
import classes from "./Sidebar.module.css";

interface NavbarLinkProps {
  icon: Icon;
  label: string;
  url: string;
  active?: boolean;
}

function NavbarLink({ url, icon: Icon, label }: NavbarLinkProps) {
  const match = useMatchRoute();
  return (
    <Tooltip label={label} position="right">
      <Link
        to={url}
        className={cx(classes.link, {
          [classes.active]: match({ to: url, fuzzy: true }) !== false,
        })}
      >
        <Icon size="1.5rem" stroke={1.5} />
      </Link>
    </Tooltip>
  );
}

const linksdata = [
  { icon: IconChess, label: "Board", url: "/" },
  { icon: IconBrain, label: "Coach", url: "/coach" },
  { icon: IconTarget, label: "Practice", url: "/practice" },
  { icon: IconUser, label: "Profile", url: "/profile" },
  { icon: IconList, label: "Games", url: "/games" },
  { icon: IconBinaryTree, label: "Repertoire", url: "/repertoire" },
    { icon: IconBooks, label: "Training", url: "/training" },
    { icon: IconFiles, label: "PDF", url: "/pdf" },
    { icon: IconCloudDownload, label: "Lichess", url: "/lichess" },
  { icon: IconFiles, label: "Files", url: "/files" },
  {
    icon: IconDatabase,
    label: "Databases",
    url: "/databases",
  },
  { icon: IconCpu, label: "Engines", url: "/engines" },
];

export function SideBar() {
  const { t } = useTranslation();

  const links = linksdata.map((link) => (
    <NavbarLink {...link} label={link.label === 'Coach' ? 'Coach' : t(`SideBar.${link.label}`)} key={link.label} />
  ));

  return (
    <>
      <AppShellSection grow>
        <Stack justify="center" gap={0}>
          {links}
        </Stack>
      </AppShellSection>
      <AppShellSection>
        <Stack justify="center" gap={0}>
          <NavbarLink icon={IconSettings} label={t("SideBar.Settings")} url="/settings" />
        </Stack>
      </AppShellSection>
    </>
  );
}
