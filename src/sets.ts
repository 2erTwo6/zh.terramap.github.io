import type { BlockSet } from './types/settings';

export const sets: BlockSet[] = [
  {
    name: "宝箱",
    entries: [
      { id: 21, name: "宝箱", isTile: true },
      { id: 467, name: "宝箱（第2组）", isTile: true }
    ]
  },
  {
    name: "腐化方块",
    entries: [
      { id: 23, name: "腐化草块", isTile: true },
      { id: 24, name: "腐化短植物", isTile: true },
      { id: 25, name: "魔矿块", isTile: true },
      { id: 32, name: "腐化荆棘", isTile: true },
      { id: 112, name: "黑沙块", isTile: true },
      { id: 163, name: "紫冰块", isTile: true },
      { id: 398, name: "腐化硬化沙块", isTile: true },
      { id: 400, name: "腐化沙岩块", isTile: true },
      { id: 636, name: "腐化藤蔓", isTile: true },
      { id: 661, name: "腐化丛林草块", isTile: true }
    ]
  },
  {
    name: "猩红方块",
    entries: [
      { id: 199, name: "猩红草块", isTile: true },
      { id: 200, name: "红冰块", isTile: true },
      { id: 201, name: "猩红短植物", isTile: true },
      { id: 203, name: "猩红矿块", isTile: true },
      { id: 205, name: "猩红藤蔓", isTile: true },
      { id: 234, name: "猩红沙块", isTile: true },
      { id: 352, name: "猩红荆棘", isTile: true },
      { id: 399, name: "猩红硬化沙块", isTile: true },
      { id: 401, name: "猩红沙岩块", isTile: true },
      { id: 662, name: "猩红丛林草块", isTile: true }
    ]
  },
  {
    name: "附魔物品",
    entries: [
      { id: 55, name: "附魔回旋镖", isItem: true },
      { id: 187, name: "3x2 装饰 - 附魔剑", u: 918, v: 0, isTile: true },
      { id: 989, name: "附魔剑", isItem: true }
    ]
  },
  {
    name: "神圣方块",
    entries: [
      { id: 109, name: "神圣草块", isTile: true },
      { id: 110, name: "神圣短植物", isTile: true },
      { id: 113, name: "神圣高植物", isTile: true },
      { id: 115, name: "神圣藤蔓", isTile: true },
      { id: 116, name: "珍珠沙块", isTile: true },
      { id: 117, name: "珍珠石块", isTile: true },
      { id: 164, name: "粉冰块", isTile: true },
      { id: 402, name: "神圣硬化沙块", isTile: true },
      { id: 403, name: "神圣沙岩块", isTile: true },
      { id: 492, name: "神圣修剪草块", isTile: true }
    ]
  },
  {
    name: "生成物品的雕像",
    entries: [
      { id: 105, name: "炸弹雕像", isItem: true, u: 612, v: 0 },
      { id: 105, name: "炸弹雕像", isItem: true, u: 612, v: 162 },
      { id: 105, name: "心形雕像", isItem: true, u: 1332, v: 0 },
      { id: 105, name: "心形雕像", isItem: true, u: 1332, v: 162 },
      { id: 105, name: "星星雕像", isTile: true, u: 72, v: 0 },
      { id: 105, name: "星星雕像", isTile: true, u: 72, v: 162 }
    ]
  },
  {
    name: "生命水晶与生命果",
    entries: [
      { id: 12, name: "生命水晶", isTile: true },
      { id: 29, name: "生命水晶", isItem: true },
      { id: 236, name: "生命果", isTile: true },
      { id: 1291, name: "生命果", isItem: true },
    ]
  },
  {
    name: "上锁的宝箱",
    entries: [
      { id: 21, isTile: true, u: 72, v: 0, name: "金宝箱", variety: "Locked" },
      { id: 21, isTile: true, u: 144, v: 0, name: "暗影宝箱", variety: "Locked" },
      { id: 21, isTile: true, u: 828, v: 0, name: "丛林宝箱", variety: "Locked" },
      { id: 21, isTile: true, u: 864, v: 0, name: "腐化宝箱", variety: "Locked" },
      { id: 21, isTile: true, u: 900, v: 0, name: "猩红宝箱", variety: "Locked" },
      { id: 21, isTile: true, u: 936, v: 0, name: "神圣宝箱", variety: "Locked" },
      { id: 21, isTile: true, u: 972, v: 0, name: "冰冻宝箱", variety: "Locked" },
      { id: 21, isTile: true, u: 1296, v: 0, name: "绿色地牢宝箱", variety: "Locked" },
      { id: 21, isTile: true, u: 1368, v: 0, name: "粉色地牢宝箱", variety: "Locked" },
      { id: 21, isTile: true, u: 1440, v: 0, name: "蓝色地牢宝箱", variety: "Locked" },
      { id: 467, isTile: true, u: 468, v: 0, name: "沙漠宝箱", variety: "Locked" },
    ]
  },
  {
    name: "蜘蛛洞",
    entries: [
      { id: 62, name: "受感染的蜘蛛墙", isWall: true },
      { id: 21, name: "蛛丝覆盖的宝箱", u: 540, v: 0, isTile: true },
      { id: 939, name: "蛛丝吊索", isItem: true }
    ]
  }
]
