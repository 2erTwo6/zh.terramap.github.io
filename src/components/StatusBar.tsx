import { Space, Spin, theme } from 'antd';
import type { ReactNode } from 'react';
import type { WorldPosition } from '../lib/tileDisplayFields';
import type { WorldTile } from '../types/settings';
import TileTags from './TileTags';

interface StatusBarProps {
  isLoading: boolean;
  selectedTile: WorldTile | null;
  status?: ReactNode;
  world?: WorldPosition;
}

export function StatusBar({ isLoading, selectedTile, status, world }: StatusBarProps) {
  const {
    token: { colorBgLayout },
  } = theme.useToken();

  return (
    <Space
      size="small"
      orientation="vertical"
      style={{
        width: '100%',
        padding: '4px 16px',
        background: colorBgLayout,
      }}
    >
      <span style={{ flexShrink: 0 }}>
        <Space>
          {isLoading && <Spin />}
          {status}
          {selectedTile && (
            <TileTags selectedTile={selectedTile} world={world} />
          )}
        </Space>
      </span>
    </Space>
  );
}