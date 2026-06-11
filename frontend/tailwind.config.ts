import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        dc: {
          bg:     '#FAF7F3',
          card:   '#FFFFFF',
          subtle: '#F4EDE4',
          border: '#E8DDD0',
          accent: {
            DEFAULT: '#9B5E1A',
            light:   '#FDF3E6',
            hi:      '#C8813A',
            dark:    '#7C4A12',
          },
          text: {
            1: '#1C1409',
            2: '#6B5E52',
            3: '#A89888',
          },
          green: { DEFAULT: '#2D7D50', bg: '#EBF5EE' },
          yellow:{ DEFAULT: '#D97706', bg: '#FFFBEB' },
          red:   '#B91C1C',
        },
      },
      fontFamily: {
        sans: [
          '-apple-system', 'BlinkMacSystemFont',
          '"PingFang SC"', '"Hiragino Sans GB"',
          '"Microsoft YaHei"', 'sans-serif',
        ],
      },
      maxWidth: { content: '860px' },
    },
  },
  plugins: [],
}

export default config
