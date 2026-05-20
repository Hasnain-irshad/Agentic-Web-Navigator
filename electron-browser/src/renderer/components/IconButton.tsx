import React from 'react';
import { IconType } from 'react-icons';

interface IconButtonProps {
  icon?: IconType;
  text?: string;
  onClick?: () => void;
  tooltip?: string;
  size?: number;
  color?: string;
  gap?: number;
}

const IconButton: React.FC<IconButtonProps> = ({
  icon: Icon,
  text,
  onClick,
  tooltip,
  size = 20,
  color = '#fff',
  gap = 6,
}) => {
  return (
    <button
      onClick={onClick}
      title={tooltip}
      style={{
        backgroundColor: '#00000000',
        color,
        border: 'none',
        padding: '8px 14px',
        borderRadius: 20,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap,
        fontSize: 14,
        fontWeight: 500,
      }}
    >
      {Icon && <Icon size={size} color={color} />}
      {text && <span>{text}</span>}
    </button>
  );
};

export default IconButton;
