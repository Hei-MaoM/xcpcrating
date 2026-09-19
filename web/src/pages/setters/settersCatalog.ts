/** Curated setter-group catalog. Not produced by export_web; keep it out of public/data. */
export interface SetterGroupRecord {
  id: string
  name: string
  contestIds: readonly string[]
}

export const SETTER_GROUPS: readonly SetterGroupRecord[] = [
  {
    id: 'uestc',
    name: '电子科技大学出题组',
    contestIds: [
      'ccpc/ccpc2024/ccpc2024harbin',
      'icpc/icpc2024/icpc2024chengdu',
      'icpc/icpc2025/icpc2025chengdu',
    ],
  },
  {
    id: 'zju',
    name: '浙江大学出题组',
    contestIds: [
      'icpc/icpc2024/icpc2024hongkong',
      'icpc/icpc2025/icpc2025hongkong',
      'ccpc/ccpc2025/ccpc2025zhengzhou',
    ],
  },
  {
    id: 'sua',
    name: 'SUA 程序设计竞赛命题组',
    contestIds: [
      'icpc/icpc2024/icpc2024nanjing',
      'icpc/icpc2024/icpc2024hangzhou',
      'icpc/icpc2025/icpc2025nanjing',
    ],
  },
  {
    id: 'neu',
    name: '东北大学出题组',
    contestIds: [
      'icpc/icpc2024/icpc2024shenyang',
      'icpc/icpc2025/icpc2025shenyang',
    ],
  },
  {
    id: 'heibingcha',
    name: '黑冰茶命题组',
    contestIds: [
      'icpc/icpc2024/icpc2024kunming',
      'icpc/icpc2025/icpc2025wuhan',
    ],
  },
  {
    id: 'tsinghua',
    name: '清华大学出题组',
    contestIds: [
      'ccpc/ccpc2024/ccpc2024chongqing',
      'icpc/icpc2025/icpc2025shanghai',
    ],
  },
  {
    id: 'fudan',
    name: '复旦大学出题组',
    contestIds: ['ccpc/ccpc2025/ccpc2025chongqing'],
  },
  {
    id: 'hit',
    name: '哈尔滨工业大学出题组',
    contestIds: ['ccpc/ccpc2025/ccpc2025harbin'],
  },
  {
    id: 'nju',
    name: '南京大学出题组',
    contestIds: ['ccpc/ccpc2024/ccpc2024zhengzhou'],
  },
  {
    id: 'sjtu',
    name: '上海交通大学出题组',
    contestIds: ['ccpc/ccpc2024/ccpc2024jinan'],
  },
  {
    id: 'sysu',
    name: '中山大学出题组',
    contestIds: ['ccpc/ccpc2025/ccpc2025jinan'],
  },
  {
    id: 'cfz',
    name: 'Cfz 出题组',
    contestIds: ['icpc/icpc2025/icpc2025xi_an'],
  },
  {
    id: 'metropolis',
    name: 'metropolis',
    contestIds: ['icpc/icpc2024/icpc2024shanghai'],
  },
]