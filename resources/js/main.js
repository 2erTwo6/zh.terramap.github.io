// --- 核心 DOM 元素 ---
var canvasContainer = document.querySelector("#canvasContainer");
var panzoomContainer = document.querySelector("#panzoomContainer");
var canvas = document.querySelector("#canvas");
var overlayCanvas = document.querySelector("#overlayCanvas");
var selectionCanvas = document.querySelector("#selectionCanvas");
var ctx = canvas.getContext("2d");
var overlayCtx = overlayCanvas.getContext("2d");
var selectionCtx = selectionCanvas.getContext("2d");
var pixels = null;

// --- 图像平滑设置 (彻底禁用，保持像素清晰) ---
[ctx, overlayCtx, selectionCtx].forEach(c => {
    c.msImageSmoothingEnabled = false;
    c.mozImageSmoothingEnabled = false;
    c.imageSmoothingEnabled = false;
});

var file, world, selectionX = 0, selectionY = 0;

// --- 虚拟滚动系统变量 (彻底修复卡顿) ---
var allOptionsData = [];      // 存储所有原始对象
var filteredOptions = [];     // 存储当前搜索过滤后的数据
var selectedKeys = new Set(); // 存储选中项的唯一标识 (type_id_u_v)
var lastSelectedIndex = -1;   // 用于 Shift 连选
const ITEM_HEIGHT = 32;       // 列表项高度

// --- 初始化 Panzoom ---
var panzoom = $("#panzoomContainer").panzoom({
    cursor: "default",
    maxScale: 20,
    increment: 0.3,
});

$("#status").html("正在检查文件API...");
if (window.File && window.FileReader && window.FileList && window.Blob) {
    $("#file").css("visibility", "visible").on('change', fileNameChanged);
    $("#status").html("请选择一个泰拉瑞亚 .wld 文件。");
} else {
    $("#status").html("当前浏览器不支持完整的文件API。");
}

// --- 1. 高性能虚拟列表引擎 ---
const vContainer = document.getElementById('virtual-blocks-container');
const vPhantom = document.getElementById('v-phantom');
const vList = document.getElementById('v-list');

function updateVirtualList() {
    if (!vContainer) return;
    const scrollTop = vContainer.scrollTop;
    const containerHeight = vContainer.clientHeight;
    
    vPhantom.style.height = (filteredOptions.length * ITEM_HEIGHT) + 'px';
    
    const start = Math.floor(scrollTop / ITEM_HEIGHT);
    const end = start + Math.ceil(containerHeight / ITEM_HEIGHT);
    const visibleData = filteredOptions.slice(start, end + 1);
    
    vList.style.transform = `translate3d(0, ${start * ITEM_HEIGHT}px, 0)`;
    vList.innerHTML = visibleData.map((item, i) => {
        const key = `${item.type}_${item.id}_${item.u}_${item.v}`;
        const isSelected = selectedKeys.has(key);
        return `<div class="virtual-item ${isSelected ? 'selected' : ''}" data-key="${key}" data-idx="${start + i}">
            ${item.text}
        </div>`;
    }).join('');
}

// 绑定滚动事件
vContainer.addEventListener('scroll', updateVirtualList);

// 绑定点击事件 (实现原生 Select 逻辑：单选, Ctrl多选, Shift连选)
vList.addEventListener('click', e => {
    const el = e.target.closest('.virtual-item');
    if (!el) return;

    const key = el.dataset.key;
    const currentIndex = parseInt(el.dataset.idx);

    if (e.ctrlKey || e.metaKey) {
        // Ctrl + 点击: 切换选中
        if (selectedKeys.has(key)) selectedKeys.delete(key);
        else selectedKeys.add(key);
    } else if (e.shiftKey && lastSelectedIndex !== -1) {
        // Shift + 点击: 连选
        const start = Math.min(lastSelectedIndex, currentIndex);
        const end = Math.max(lastSelectedIndex, currentIndex);
        for (let i = start; i <= end; i++) {
            const item = filteredOptions[i];
            selectedKeys.add(`${item.type}_${item.id}_${item.u}_${item.v}`);
        }
    } else {
        // 直接点击: 单选
        selectedKeys.clear();
        selectedKeys.add(key);
    }

    lastSelectedIndex = currentIndex;
    updateVirtualList();
});

// 搜索逻辑
$('#blocksFilter').on('input', function() {
    const val = $(this).val().toLowerCase();
    filteredOptions = allOptionsData.filter(item => item.text.toLowerCase().includes(val));
    vContainer.scrollTop = 0;
    updateVirtualList();
});

// --- 2. 还原所有数据收集逻辑 ---
function addTileSelectOptions() {
    for(var i = 0; i < settings.Tiles.length; i++) {
        var tile = settings.Tiles[i];
        allOptionsData.push({ text: `${tile.Name} (方块 ${i})`, id: i, type: 'tile', u: null, v: null });
        if(tile.Frames) {
            for(var frameIndex = 0; frameIndex < tile.Frames.length; frameIndex++) {
                var frame = tile.Frames[frameIndex];
                var text = tile.Name;
                if(frame.Name) text = `${frame.Name} - ${text}`;
                if(frame.Variety) text = `${frame.Variety} - ${text}`;
                allOptionsData.push({ text: `${text} (方块 ${i})`, id: i, type: 'tile', u: frame.U, v: frame.V });
            }
        }
    }
}

function addItemSelectOptions() {
    for(var i = 0; i < settings.Items.length; i++) {
        var item = settings.Items[i];
        allOptionsData.push({ text: `${item.Name} (物品 ${item.Id})`, id: item.Id, type: 'item', u: null, v: null });
    }
}

function addWallSelectOptions() {
    for(var i = 0; i < settings.Walls.length; i++) {
        var wall = settings.Walls[i];
        allOptionsData.push({ text: `${wall.Name} (墙壁)`, id: wall.Id, type: 'wall', u: null, v: null });
    }
}

function collectOptions() {
    addTileSelectOptions();
    addItemSelectOptions();
    addWallSelectOptions();
    allOptionsData.sort((a,b) => a.text < b.text ? -1 : 1);
    filteredOptions = allOptionsData;
    $("#v-count").text(`已加载 ${allOptionsData.length} 个项目`);
    updateVirtualList();
}

// --- 3. 还原完整的泰拉瑞亚核心逻辑 ---

function getSelectedInfos() {
    var selectedInfos = [];
    selectedKeys.forEach(key => {
        var parts = key.split('_');
        var type = parts[0], id = parts[1];
        var u = parts[2] === 'null' ? null : parts[2], v = parts[3] === 'null' ? null : parts[3];
        
        if(type === 'tile') selectedInfos.push(getTileInfoFrom(id, u, v));
        else if(type === 'item') selectedInfos.push(settings.Items.find(i => i.Id == id));
        else if(type === 'wall') selectedInfos.push(settings.Walls.find(w => w.Id == id));
    });
    return selectedInfos.filter(i => i);
}

function getTileInfoFrom(id, u, v) {
    var tileInfo = settings.Tiles[id];
    if(tileInfo && tileInfo.Frames) {
        for(var i = 0; i < tileInfo.Frames.length; i++) {
            var f = tileInfo.Frames[i];
            if(u == f.U && v == f.V) { f.parent = tileInfo; f.isTile = true; return f; }
        }
    }
    if(tileInfo) tileInfo.isTile = true;
    return tileInfo;
}

function isTileMatch(tile, selectedInfos) {
    for(var j = 0; j < selectedInfos.length; j++) {
        var info = selectedInfos[j];
        if(!info) continue;
        if(tile.info && info.isTile && (tile.info == info || (!info.parent && tile.Type == info.Id))) return true;
        if(info.isWall && tile.WallType == info.Id) return true;
        if(tile.chest && info.isItem) {
            for(var i = 0; i < tile.chest.items.length; i++) if(info.Id == tile.chest.items[i].id) return true;
        }
        let te = tile.tileEntity;
        if (te && info.isItem) {
            if ([1, 4, 6].includes(te.type)) { if (info.Id == te.item.id) return true; }
            else if ([3, 5].includes(te.type)) {
                for (let k = 0; k < te.items.length; k++) {
                    if (info.Id == te.items[k].id || (te.dyes && te.dyes[k] && info.Id == te.dyes[k].id)) return true;
                }
            }
        }
    }
    return false;
}

function highlightAll() {
    if(!world) return;
    var selectedInfos = getSelectedInfos();
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    overlayCtx.fillStyle = "rgba(0, 0, 0, 0.75)";
    overlayCtx.fillRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    if(selectedInfos.length > 0) {
        var x = 0, y = 0;
        for(var i = 0; i < world.tiles.length; i++) {
            if(isTileMatch(world.tiles[i], selectedInfos)) {
                overlayCtx.fillStyle = "#fff";
                overlayCtx.fillRect(x, y, 1, 1);
            }
            y++; if(y >= world.height) { y = 0; x++; }
        }
    }
}

function highlightSet(setIndex) {
    var set = sets[setIndex];
    selectedKeys.clear();
    allOptionsData.forEach(item => {
        if (item.type !== 'tile') return;
        var match = set.Entries.some(e => ((e.Id && e.Id == item.id) || (e.parent && e.parent.Id == item.id)) && (!e.U || e.U == item.u) && (!e.V || e.V == item.v));
        if (match) selectedKeys.add(`${item.type}_${item.id}_${item.u}_${item.v}`);
    });
    updateVirtualList();
    highlightAll();
}

// --- 4. 渲染与 Worker 逻辑 ---

function getTileColor(y, tile, world) {
    if(tile.IsActive) return tileColors[tile.Type][0];
    if (tile.IsLiquidPresent) {
        if(tile.IsLiquidLava) return liquidColors[1];
        if (tile.IsLiquidHoney) return liquidColors[2];
        if (tile.Shimmer) return { r: 155, g: 112, b: 233 };
        return liquidColors[0];
    }
    if (tile.IsWallPresent) return wallColors[tile.WallType][0];
    if(y < world.worldSurfaceY) return { r: 132, g: 170, b: 248 };
    if(y < world.rockLayerY) return { r: 88, g: 61, b: 46 };
    if(y < world.hellLayerY) return { r: 74, g: 67, b: 60 };
    return { r: 0, g: 0, b: 0 };
}

function onWorldLoaderWorkerMessage(e) {
    if(e.data.status) $("#status").html(e.data.status);
    if (e.data.tiles) {
        const bufferWidth = 200;
        if (!pixels) pixels = new Uint8ClampedArray(4 * bufferWidth * world.height);
        let xlimit = e.data.x + e.data.tiles.length / world.height;
        let i = 0;
        for (let x = e.data.x; x < xlimit; x++) {
            const bStart = bufferWidth * Math.floor(x / bufferWidth);
            if (x % bufferWidth === 0 && x > 0) ctx.putImageData(new ImageData(pixels, bufferWidth), bStart - bufferWidth, 0);
            for (let y = 0; y < world.height; y++) {
                let t = e.data.tiles[i++];
                if (t) {
                    t.info = getTileInfo(t);
                    world.tiles.push(t);
                    let c = getTileColor(y, t, world) || { r: 0, g: 0, b: 0 };
                    const pxIdx = 4 * (y * bufferWidth + x - bStart);
                    pixels[pxIdx] = c.r; pixels[pxIdx+1] = c.g; pixels[pxIdx+2] = c.b; pixels[pxIdx+3] = 255;
                }
            }
        }
    }
    if (e.data.done) {
        const bStart = 200 * Math.floor((world.width - 1) / 200);
        if (pixels) ctx.putImageData(new ImageData(pixels, 200), bStart, 0);
        pixels = null; $("#status").html("加载完成。");
    }
    if(e.data.chests) {
        world.chests = e.data.chests;
        e.data.chests.forEach(c => {
            let idx = c.x * world.height + c.y;
            [idx, idx+1, idx+world.height, idx+world.height+1].forEach(p => { if(world.tiles[p]) world.tiles[p].chest = c; });
        });
    }
    if(e.data.signs) {
        world.signs = e.data.signs;
        e.data.signs.forEach(s => {
            let idx = s.x * world.height + s.y;
            [idx, idx+1, idx+world.height, idx+world.height+1].forEach(p => { if(world.tiles[p]) world.tiles[p].sign = s; });
        });
    }
    if(e.data.npcs) addNpcs(e.data.npcs);
    if (e.data.tileEntities) {
        for (const [pos, entity] of e.data.tileEntities.entries()) {
            let idx = pos.x * world.height + pos.y;
            let tile = world.tiles[idx];
            if (tile && tile.info) {
                let sizeX = 1, sizeY = 1;
                if (tile.info.Size) { sizeX = tile.info.Size[0] - '0'; sizeY = tile.info.Size[2] - '0'; }
                for (let x = 0; x < sizeX; x++) {
                    for (let y = 0; y < sizeY; y++) {
                        let p = (pos.x+x) * world.height + pos.y+y;
                        if(world.tiles[p]) world.tiles[p].tileEntity = entity;
                    }
                }
            }
        }
    }
    if(e.data.world) {
        world = e.data.world; world.tiles = [];
        [panzoomContainer, canvas, overlayCanvas, selectionCanvas].forEach(c => { c.width = world.width; c.height = world.height; });
        resizeCanvases();
        $("#worldPropertyList").empty();
        Object.keys(world).forEach(k => { if(typeof world[k] !== 'object') $("#worldPropertyList").append(`<li>${k}: ${world[k]}</li>`); });
    }
}

// --- 5. UI 交互逻辑 ---

function getTileInfo(tile) {
    var info = settings.Tiles[tile.Type];
    if(!info || !info.Frames) return info;
    var match;
    for(var i = 0; i < info.Frames.length; i++) {
        var f = info.Frames[i];
        if((!f.U && !tile.TextureU) || f.U <= tile.TextureU) {
            if((!f.V && !tile.TextureV) || f.V <= tile.TextureV) match = f;
        }
    }
    if(match) match.parent = info;
    return match || info;
}

function getTileText (tile) {
    if(!tile) return "无";
    var text = "无";
    if(tile.info) {
        text = tile.info.parent ? `${tile.info.parent.Name}${tile.info.Name ? ' - ' + tile.info.Name : ''}` : tile.info.Name;
        if (tile.tileEntity) {
            let te = tile.tileEntity;
            if([1,4,6].includes(te.type)) text += ` - ${getItemText(te.item)}`;
            else if(te.type === 2) text += ` - ${tile.info.CheckTypes[te.logicCheckType]}, ${te.on ? "开" : "关"}`;
        }
    } else if (tile.WallType !== undefined) {
        text = (tile.WallType < settings.Walls.length) ? `${settings.Walls[tile.WallType].Name} (${tile.WallType})` : `未知墙壁 (${tile.WallType})`;
    }
    if (tile.IsLiquidPresent) {
        let l = tile.IsLiquidLava ? "熔岩" : (tile.IsLiquidHoney ? "蜂蜜" : (tile.Shimmer ? "微光" : "水"));
        text = (text === "无") ? l : `${text} ${l}`;
    }
    if(tile.IsRedWirePresent) text += " (红线)";
    if(tile.IsGreenWirePresent) text += " (绿线)";
    if(tile.IsBlueWirePresent) text += " (蓝线)";
    if(tile.IsYellowWirePresent) text += " (黄线)";
    return text;
}

function getItemText(item) {
    let p = (item.prefixId > 0 && item.prefixId < settings.ItemPrefix.length) ? settings.ItemPrefix[item.prefixId].Name : "";
    let n = item.id;
    for(let i = 0; i < settings.Items.length; i++) if(Number(settings.Items[i].Id) === item.id) { n = settings.Items[i].Name; break; }
    return `${p} ${n} (${item.count})`.trim();
}

panzoomContainer.addEventListener('mousemove', evt => {
    if(!world || !world.tiles) return;
    var pos = getMousePos(panzoomContainer, evt);
    var t = world.tiles[pos.x * world.height + pos.y];
    if(t) $("#status").html(`${getTileText(t)} (${pos.x}, ${pos.y})`);
});

$("#panzoomContainer").on('panzoomend', function(evt, panzoom, matrix, changed) {
    if (changed) return;
    var pos = getMousePos(panzoomContainer, evt);
    selectionX = pos.x; selectionY = pos.y;
    drawSelectionIndicator();
    var t = world.tiles[selectionX * world.height + selectionY];
    if(t) {
        $("#tileInfoList").empty();
        $("#tile").html(getTileText(t));
        if(t.chest) t.chest.items.forEach(i => $("#tileInfoList").append(`<li>${getItemText(i)}</li>`));
        if(t.tileEntity && [3,5].includes(t.tileEntity.type)) t.tileEntity.items.forEach(i => { if(i.id > 0) $("#tileInfoList").append(`<li>${getItemText(i)}</li>`); });
        if(t.sign && t.sign.text) $("#tileInfoList").append(`<li>${t.sign.text}</li>`);
    }
});

function getMousePos(c, e) {
    var rect = panzoomContainer.getBoundingClientRect();
    var scale = rect.width / panzoomContainer.width;
    return { x: Math.floor((e.clientX - rect.left) / scale), y: Math.floor((e.clientY - rect.top) / scale) };
}

function drawSelectionIndicator() {
    selectionCtx.clearRect(0, 0, selectionCanvas.width, selectionCanvas.height);
    selectionCtx.lineWidth = 12; selectionCtx.strokeStyle="red";
    selectionCtx.strokeRect(selectionX - 19, selectionY - 19, 39, 39);
}

function resizeCanvases() {
    var w = window.innerWidth * 0.99;
    var h = w * (panzoomContainer.height/panzoomContainer.width);
    [panzoomContainer, canvas, overlayCanvas, selectionCanvas].forEach(c => { c.style.width = w+'px'; c.style.height = h+'px'; });
}

function fileNameChanged (e) { file = e.target.files[0]; $("#help").hide(); reloadWorld(); }
function reloadWorld() { var w = new Worker('resources/js/WorldLoader.js'); w.addEventListener('message', onWorldLoaderWorkerMessage); w.postMessage(file); }
function addNpcs(npcs) { world.npcs = npcs; npcs.forEach(n => $("#npcList").append(`<li><a href="#" onclick="selectPoint(${n.x}, ${n.y})">${n.name}</a></li>`)); }
function selectPoint(x, y) { selectionX = x; selectionY = y; drawSelectionIndicator(); }
function resetPanZoom() { panzoom.panzoom('reset'); }
function clearHighlight() { overlayCtx.clearRect(0,0,overlayCanvas.width,overlayCanvas.height); selectionCtx.clearRect(0,0,selectionCanvas.width,selectionCanvas.height); }

function saveMapImage() {
    var nc = document.createElement("canvas"); nc.width = world.width; nc.height = world.height;
    var nctx = nc.getContext("2d"); nctx.drawImage(canvas,0,0); nctx.drawImage(overlayCanvas,0,0); nctx.drawImage(selectionCanvas,0,0);
    nc.toBlob(b => saveAs(b, `${world.name}.png`));
}

function findBlock(direction) {
    if(!world) return;
    var x = selectionX, y = selectionY + direction;
    var start = x * world.height + y;
    var infos = getSelectedInfos();
    if(infos.length > 0) {
        for(var i = start; i >= 0 && i < world.tiles.length; i += direction) {
            if(isTileMatch(world.tiles[i], infos)) { selectionX = x; selectionY = y; drawSelectionIndicator(); break; }
            y += direction;
            if(y < 0 || y >= world.height) { y = (direction > 0) ? 0 : world.height - 1; x += direction; }
        }
    }
}
function previousBlock() { findBlock(-1); }
function nextBlock() { findBlock(1); }

// --- 启动初始化 ---
$(function() {
    collectOptions();
    sets.forEach((s, i) => $("#setList").append(`<li><a href="#" onclick="highlightSet(${i})">${s.Name}</a></li>`));
    $(window).on('resize load', () => $('body').css('padding-top', parseInt($('#main-navbar').css("height"))+10));
    panzoom.parent().on('mousewheel.focal', function(e) {
        e.preventDefault();
        const delta = e.delta || e.originalEvent.wheelDelta;
        panzoom.panzoom('zoom', delta < 0, { increment: 0.3, animate: true, focal: e });
    });
});
