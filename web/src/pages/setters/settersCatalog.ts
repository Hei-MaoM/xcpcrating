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
      'ccpc/ccpc2022/ccpc2022weihai',
      'ccpc/ccpc2024/ccpc2024harbin',
      'icpc/icpc2024/icpc2024chengdu',
      'icpc/icpc2025/icpc2025chengdu',
    ],
  },
  {
    id: 'zju',
    name: '浙江大学出题组',
    contestIds: [
      'ccpc/ccpc2021/ccpc2021guilin',
      'ccpc/ccpc2023/ccpc2023guilin',
      'ccpc/ccpc2025/ccpc2025zhengzhou',
      'icpc/icpc2022/icpc2022hangzhou',
      'icpc/icpc2022/icpc2022hongkong',
      'icpc/icpc2023/icpc2023hangzhou',
      'icpc/icpc2024/icpc2024hongkong',
      'icpc/icpc2025/icpc2025hongkong',
    ],
  },
  {
    id: 'sua',
    name: 'SUA 程序设计竞赛命题组',
    contestIds: [
      'icpc/icpc2021/icpc2021macau',
      'icpc/icpc2022/icpc2022nanjing',
      'icpc/icpc2023/icpc2023jinan',
      'icpc/icpc2023/icpc2023nanjing',
      'icpc/icpc2024/icpc2024hangzhou',
      'icpc/icpc2024/icpc2024nanjing',
      'icpc/icpc2025/icpc2025ecfinal',
      'icpc/icpc2025/icpc2025nanjing',
    ],
  },
  {
    id: 'neu',
    name: '东北大学出题组',
    contestIds: [
      'icpc/icpc2022/icpc2022shenyang',
      'icpc/icpc2023/icpc2023shenyang',
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
      'ccpc/ccpc2023/ccpc2023shenzhen',
      'ccpc/ccpc2024/ccpc2024chongqing',
      'icpc/icpc2025/icpc2025shanghai',
    ],
  },
  {
    id: 'fudan',
    name: '复旦大学出题组',
    contestIds: [
      'ccpc/ccpc2023/ccpc2023harbin',
      'ccpc/ccpc2025/ccpc2025chongqing',
      'ccpc/ccpc2025/ccpc2025preliminary',
    ],
  },
  {
    id: 'hit',
    name: '哈尔滨工业大学出题组',
    contestIds: [
      'ccpc/ccpc2025/ccpc2025harbin',
    ],
  },
  {
    id: 'nju',
    name: '南京大学出题组',
    contestIds: [
      'ccpc/ccpc2022/ccpc2022mianyang',
      'ccpc/ccpc2024/ccpc2024zhengzhou',
      'icpc/icpc2023/icpc2023macau',
    ],
  },
  {
    id: 'sjtu',
    name: '上海交通大学出题组',
    contestIds: [
      'ccpc/ccpc2022/ccpc2022guilin',
      'ccpc/ccpc2024/ccpc2024jinan',
    ],
  },
  {
    id: 'sysu',
    name: '中山大学出题组',
    contestIds: [
      'ccpc/ccpc2023/ccpc2023qinhuangdao',
      'ccpc/ccpc2025/ccpc2025jinan',
    ],
  },
  {
    id: 'cfz',
    name: 'Cfz 出题组',
    contestIds: [
      'icpc/icpc2025/icpc2025xi_an',
    ],
  },
  {
    id: 'metropolis',
    name: 'metropolis',
    contestIds: [
      'icpc/icpc2024/icpc2024shanghai',
    ],
  },
  {
    id: 'ustc',
    name: '中国科学技术大学出题组',
    contestIds: [
      'icpc/icpc2023/icpc2023hefei',
    ],
  },
  {
    id: 'pku',
    name: '北京大学出题组',
    contestIds: [
      'ccpc/ccpc2021/ccpc2021guangzhou',
      'ccpc/ccpc2022/ccpc2022guangzhou',
      'icpc/icpc2025/icpc2025preliminary-1',
    ],
  },
  {
    id: 'nfls',
    name: '南京外国语学校出题组',
    contestIds: [
      'icpc/icpc2023/icpc2023xi_an',
    ],
  },
  {
    id: 'hdu',
    name: '杭州电子科技大学出题组',
    contestIds: [
      'icpc/icpc2023/icpc2023preliminary-1',
      'icpc/icpc2025/icpc2025preliminary-2',
    ],
  },
  {
    id: 'bupt',
    name: '北京邮电大学出题组',
    contestIds: [
      'ccpc/ccpc2024/ccpc2024preliminary',
    ],
  },
]
