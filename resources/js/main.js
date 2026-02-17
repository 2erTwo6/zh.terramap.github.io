/* ================================================================
 *  main.js  —  TerraMap（虚拟滚动列表版）
 * ================================================================ */

var canvasContainer = document.querySelector("#canvasContainer");
var panzoomContainer = document.querySelector("#panzoomContainer");

var canvas = document.querySelector("#canvas");
var overlayCanvas = document.querySelector("#overlayCanvas");
var selectionCanvas = document.querySelector("#selectionCanvas");

var ctx = canvas.getContext("2d");
var overlayCtx = overlayCanvas.getContext("2d");
var selectionCtx = selectionCanvas.getContext("2d");

var pixels = null;

ctx.msImageSmoothingEnabled = false;
ctx.mozImageSmoothingEnabled = false;
ctx.imageSmoothingEnabled = false;

overlayCtx.msImageSmoothingEnabled = false;
overlayCtx.mozImageSmoothingEnabled = false;
overlayCtx.imageSmoothingEnabled = false;

selectionCtx.msImageSmoothingEnabled = false;
selectionCtx.mozImageSmoothingEnabled = false;
selectionCtx.imageSmoothingEnabled = false;

var file;
var world;

var selectionX = 0;
var selectionY = 0;

var panzoom = $("#panzoomContainer").panzoom({
  cursor: "default",
  maxScale: 20,
  increment: 0.3,
});

$("#status").html("Checking File APIs...");

if (window.File && window.FileReader && window.FileList && window.Blob) {
  $("#file").css("visibility", "visible");
  $("#file").on('change', fileNameChanged);
  $("#status").html("Please choose a Terraria .wld file.");
} else {
  $("#status").html("The File APIs are not fully supported in this browser.");
}

resizeCanvases();

/* ================================================================
 *  虚拟滚动选择列表 (VirtualSelect)
 * ================================================================ */
var VirtualSelect = (function () {
  var allItems = [];        // 全部选项数据 [{text, value, u, v}, ...]
  var filteredItems = [];   // 过滤后
  var selectedSet = new Set(); // 选中项的 key 集合
  var ITEM_HEIGHT = 26;     // 每项高度 px
  var container = null;
  var viewport = null;
  var content = null;
  var lastRenderedRange = null;

  function itemKey(item) {
    return item.value + '|' + (item.u || '') + '|' + (item.v || '');
  }

  function init(containerEl, items) {
    container = containerEl;
    allItems = items;
    filteredItems = items;
    selectedSet.clear();

    container.innerHTML = '';

    viewport = document.createElement('div');
    viewport.className = 'vlist-viewport';

    content = document.createElement('div');
    content.className = 'vlist-content';

    viewport.appendChild(content);
    container.appendChild(viewport);

    viewport.addEventListener('scroll', onScroll);
    lastRenderedRange = null;
    render();
  }

  var scrollRafId = null;
  function onScroll() {
    if (scrollRafId) return;
    scrollRafId = requestAnimationFrame(function () {
      scrollRafId = null;
      render();
    });
  }

  function render() {
    if (!viewport || !content) return;

    var scrollTop = viewport.scrollTop;
    var viewHeight = viewport.clientHeight || 350;
    var totalHeight = filteredItems.length * ITEM_HEIGHT;

    content.style.height = totalHeight + 'px';

    var startIdx = Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - 3);
    var endIdx = Math.min(filteredItems.length, Math.ceil((scrollTop + viewHeight) / ITEM_HEIGHT) + 3);

    // 如果渲染范围没变且没有选中状态变化，跳过
    if (lastRenderedRange &&
        lastRenderedRange.start === startIdx &&
        lastRenderedRange.end === endIdx &&
        lastRenderedRange.selSize === selectedSet.size) {
      return;
    }
    lastRenderedRange = { start: startIdx, end: endIdx, selSize: selectedSet.size };

    var fragment = document.createDocumentFragment();

    for (var i = startIdx; i < endIdx; i++) {
      var item = filteredItems[i];
      var key = itemKey(item);
      var isSelected = selectedSet.has(key);

      var div = document.createElement('div');
      div.className = 'v-item' + (isSelected ? ' selected' : '');
      div.textContent = item.text;
      div.style.height = ITEM_HEIGHT + 'px';
      div.style.lineHeight = ITEM_HEIGHT + 'px';
      div.style.top = (i * ITEM_HEIGHT) + 'px';
      div.setAttribute('data-idx', i);
      fragment.appendChild(div);
    }

    // 一次性替换内容
    // 保留 content 元素本身，只清空子节点
    while (content.firstChild) {
      content.removeChild(content.firstChild);
    }
    content.appendChild(fragment);
  }

  // 事件委托处理点击
  function setupClickHandler() {
    // 延迟到 DOM 就绪后调用
    document.addEventListener('click', function (e) {
      var target = e.target;
      if (!target.classList || !target.classList.contains('v-item')) return;
      if (!container || !container.contains(target)) return;

      var idx = parseInt(target.getAttribute('data-idx'), 10);
      if (isNaN(idx) || idx < 0 || idx >= filteredItems.length) return;

      var item = filteredItems[idx];
      var key = itemKey(item);

      if (e.ctrlKey || e.metaKey) {
        // Ctrl/Cmd + 点击：切换单项
        if (selectedSet.has(key)) {
          selectedSet.delete(key);
        } else {
          selectedSet.add(key);
        }
      } else if (e.shiftKey && lastClickedIdx >= 0) {
        // Shift + 点击：范围选择
        var from = Math.min(lastClickedIdx, idx);
        var to = Math.max(lastClickedIdx, idx);
        for (var i = from; i <= to; i++) {
          selectedSet.add(itemKey(filteredItems[i]));
        }
      } else {
        // 普通点击：单选
        selectedSet.clear();
        selectedSet.add(key);
      }

      lastClickedIdx = idx;
      lastRenderedRange = null; // 强制重新渲染
      render();
      updateCountBadge();
    });
  }
  var lastClickedIdx = -1;

  function updateCountBadge() {
    var badge = document.getElementById('selectedCount');
    if (badge) {
      badge.textContent = '已选: ' + selectedSet.size;
    }
  }

  function filter(search) {
    if (!search) {
      filteredItems = allItems;
    } else {
      var searchLower = search.toLowerCase();
      // 先尝试简单子串匹配（更快），如果包含正则特殊字符才用正则
      var hasRegexChars = /[\\^$.*+?()[\]{}|]/.test(search);
      if (hasRegexChars) {
        try {
          var regex = new RegExp(search, "gi");
          filteredItems = [];
          for (var i = 0; i < allItems.length; i++) {
            if (regex.test(allItems[i].text)) {
              filteredItems.push(allItems[i]);
              regex.lastIndex = 0;
            }
          }
        } catch (e) {
          return;
        }
      } else {
        filteredItems = [];
        for (var i = 0; i < allItems.length; i++) {
          if (allItems[i].text.toLowerCase().indexOf(searchLower) !== -1) {
            filteredItems.push(allItems[i]);
          }
        }
      }
    }
    viewport.scrollTop = 0;
    lastRenderedRange = null;
    render();
  }

  function getSelected() {
    var result = [];
    for (var i = 0; i < allItems.length; i++) {
      if (selectedSet.has(itemKey(allItems[i]))) {
        result.push(allItems[i]);
      }
    }
    return result;
  }

  function setSelectedByInfos(infos) {
    selectedSet.clear();
    // 根据 infos 里的信息找到对应的 allItems 并选中
    for (var i = 0; i < allItems.length; i++) {
      var item = allItems[i];
      var tileInfo = getTileInfoFrom(item.value, item.u, item.v);

      if (tileInfo && infos.some(function (entry) {
        return (
          ((entry.Id && entry.Id === tileInfo.Id) ||
            (entry.parent && tileInfo.parent && entry.parent.Id === tileInfo.parent.Id)) &&
          (!entry.U || entry.U === tileInfo.U) &&
          (!entry.V || entry.V === tileInfo.V)
        );
      })) {
        selectedSet.add(itemKey(item));
      }
    }
    lastRenderedRange = null;
    render();
    updateCountBadge();
  }

  function selectAll() {
    for (var i = 0; i < filteredItems.length; i++) {
      selectedSet.add(itemKey(filteredItems[i]));
    }
    lastRenderedRange = null;
    render();
    updateCountBadge();
  }

  function clearAll() {
    selectedSet.clear();
    lastRenderedRange = null;
    render();
    updateCountBadge();
  }

  // 初始化点击事件委托
  setupClickHandler();

  return {
    init: init,
    filter: filter,
    render: render,
    getSelected: getSelected,
    setSelectedByInfos: setSelectedByInfos,
    selectAll: selectAll,
    clearAll: clearAll,
    updateCountBadge: updateCountBadge
  };
})();

/* ================================================================
 *  构建选项数据
 * ================================================================ */
var options = [];

addTileSelectOptions();
addItemSelectOptions();
addWallSelectOptions();
sortAndInitVirtualSelect();

addSetListItems();

function addSetListItems() {
  for (var i = 0; i < sets.length; i++) {
    var set = sets[i];

    for (var j = 0; j < set.Entries.length; j++) {
      var entry = set.Entries[j];
      if (entry.U || entry.V) {
        var tileInfo = getTileInfoFrom(entry.Id, entry.U, entry.V);
        if (tileInfo) {
          set.Entries[j] = tileInfo;
        }
      }
    }

    $("#setList").append('<li><a href="#" onclick="highlightSet(' + i + ')">' + set.Name + '</a></li>');
  }
}

function highlightSet(setIndex) {
  var set = sets[setIndex];

  // 设置虚拟列表的选中状态
  VirtualSelect.setSelectedByInfos(set.Entries);

  console.log({ set });

  highlightInfos(set.Entries);
}

function sortAndInitVirtualSelect() {
  options.sort(compareOptions);

  // 转换为虚拟列表的数据格式
  var items = [];
  for (var i = 0; i < options.length; i++) {
    var opt = options[i];
    items.push({
      text: opt.text,
      value: opt.value,
      u: opt.u || null,
      v: opt.v || null
    });
  }

  VirtualSelect.init(document.getElementById('virtualBlockList'), items);
}

function addTileSelectOptions() {
  for (var i = 0; i < settings.Tiles.length; i++) {
    var tile = settings.Tiles[i];
    tile.isTile = true;

    options.push({
      text: tile.Name + ' (Tile ' + i + ')',
      value: String(i),
      u: null,
      v: null
    });

    if (tile.Frames) {
      for (var frameIndex = 0; frameIndex < tile.Frames.length; frameIndex++) {
        var frame = tile.Frames[frameIndex];
        frame.isTile = true;

        var text = tile.Name;
        if (frame.Name) {
          text = frame.Name + ' - ' + text;
        }
        if (frame.Variety) {
          text = frame.Variety + ' - ' + text;
        }
        text += ' (Tile ' + i + ')';

        options.push({
          text: text,
          value: String(i),
          u: String(frame.U),
          v: String(frame.V)
        });
      }
    }
  }
}

function addItemSelectOptions() {
  for (var i = 0; i < settings.Items.length; i++) {
    var item = settings.Items[i];
    item.isItem = true;

    options.push({
      text: item.Name + ' (Item ' + item.Id + ')',
      value: 'item' + item.Id,
      u: null,
      v: null
    });
  }
}

function addWallSelectOptions() {
  for (var i = 0; i < settings.Walls.length; i++) {
    var wall = settings.Walls[i];
    wall.isWall = true;

    options.push({
      text: wall.Name + ' (Wall)',
      value: 'wall' + wall.Id,
      u: null,
      v: null
    });
  }
}

function compareOptions(a, b) {
  if (a.text < b.text) return -1;
  if (a.text > b.text) return 1;
  return 0;
}

/* ================================================================
 *  模态框与搜索框
 * ================================================================ */
$('#chooseBlocksModal').on('shown.bs.modal', function () {
  $('#blocksFilter').focus();
  // 模态框显示后触发一次渲染（确保尺寸正确）
  VirtualSelect.render();
});

$(document).bind('keydown', 'ctrl+b', function () {
  $('#chooseBlocksModal').modal();
});

// 搜索框 - 带防抖
(function () {
  var filterTimer = null;
  $('#blocksFilter').on('input', function () {
    clearTimeout(filterTimer);
    var val = $.trim($(this).val());
    filterTimer = setTimeout(function () {
      VirtualSelect.filter(val);
    }, 200);
  });
})();

/* ================================================================
 *  窗口大小调整
 * ================================================================ */
$(window).resize(function () {
  $('body').css('padding-top', parseInt($('#main-navbar').css("height")) + 10);
  $('#canvasContainer').css("overflow", "visible");
});

$(window).load(function () {
  $('body').css('padding-top', parseInt($('#main-navbar').css("height")) + 10);
});

/* ================================================================
 *  平移缩放
 * ================================================================ */
panzoom.parent().on('mousewheel.focal', onMouseWheel);

function onMouseWheel(e) {
  e.preventDefault();

  var delta = e.delta || e.originalEvent.wheelDelta;
  var zoomOut = delta ? delta < 0 : e.originalEvent.deltaY > 0;

  var isTouchPad = Math.abs(delta) < 120;
  var multiplier = isTouchPad ? 0.025 : 0.3;

  var transform = $(panzoomContainer).panzoom('getMatrix');
  var scale = transform[0];

  panzoom.panzoom('zoom', zoomOut, {
    increment: multiplier * scale,
    animate: true,
    focal: e
  });
}

$(document).bind('keydown', 'e', zoomIn);
$(document).bind('keydown', 'c', zoomOut);

function zoomIn() {
  var transform = $(panzoomContainer).panzoom('getMatrix');
  var scale = transform[0];
  panzoom.panzoom('zoom', false, {
    increment: 0.3 * scale,
    animate: true
  });
}

function zoomOut() {
  var transform = $(panzoomContainer).panzoom('getMatrix');
  var scale = transform[0];
  panzoom.panzoom('zoom', true, {
    increment: 0.3 * scale,
    animate: true
  });
}

/* ================================================================
 *  查找方块
 * ================================================================ */
function previousBlock(e) {
  findBlock(-1);
}

function nextBlock(e) {
  findBlock(1);
}

function isTileMatch(tile, selectedInfos, x, y) {
  for (var j = 0; j < selectedInfos.length; j++) {
    var info = selectedInfos[j];

    if (tile.info && info.isTile && (tile.info == info || (!info.parent && tile.Type == info.Id)))
      return true;

    if (info.isWall && tile.WallType == info.Id)
      return true;

    var chest = tile.chest;
    if (chest && info.isItem) {
      for (var i = 0; i < chest.items.length; i++) {
        var item = chest.items[i];
        if (info.Id == item.id) {
          return true;
        }
      }
    }

    var tileEntity = tile.tileEntity;
    if (tileEntity && info.isItem) {
      switch (tileEntity.type) {
        case 1:
        case 4:
        case 6:
          if (info.Id == tileEntity.item.id) {
            return true;
          }
          break;
        case 3:
        case 5:
          for (var i = 0; i < tileEntity.items.length; i++) {
            if (info.Id == tileEntity.items[i].id) return true;
            if (info.Id == tileEntity.dyes[i].id) return true;
          }
          break;
      }
    }
  }

  return false;
}

function findBlock(direction) {
  if (!world) return;

  var x = selectionX;
  var y = selectionY + direction;

  var start = x * world.height + y;

  var selectedInfos = getSelectedInfos();

  if (selectedInfos.length > 0) {
    for (var i = start; i >= 0 && i < world.tiles.length; i += direction) {
      var tile = world.tiles[i];

      if (isTileMatch(tile, selectedInfos, x, y)) {
        selectionX = x;
        selectionY = y;
        drawSelectionIndicator();
        break;
      }

      y += direction;

      if (y < 0 || y >= world.height) {
        if (direction > 0) y = 0;
        else y = world.height - 1;
        x += direction;
      }
    }
  }
}

/* ================================================================
 *  高亮
 * ================================================================ */
function highlightAll() {
  if (!world) return;
  var selectedInfos = getSelectedInfos();
  highlightInfos(selectedInfos);
}

function highlightInfos(selectedInfos) {
  var x = 0;
  var y = 0;

  overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  overlayCtx.fillStyle = "rgba(0, 0, 0, 0.75)";
  overlayCtx.fillRect(0, 0, overlayCanvas.width, overlayCanvas.height);

  if (selectedInfos.length > 0) {
    for (var i = 0; i < world.tiles.length; i++) {
      var tile = world.tiles[i];

      if (isTileMatch(tile, selectedInfos)) {
        overlayCtx.fillStyle = "rgb(255, 255, 255)";
        overlayCtx.fillRect(x, y, 1, 1);
      }

      y++;
      if (y >= world.height) {
        y = 0;
        x++;
      }
    }
  }
}

/* ================================================================
 *  获取已选信息（从虚拟列表）
 * ================================================================ */
function getSelectedInfos() {
  var selectedItems = VirtualSelect.getSelected();
  var selectedInfos = [];

  for (var j = 0; j < selectedItems.length; j++) {
    var item = selectedItems[j];

    var tileInfo = getTileInfoFrom(item.value, item.u, item.v);
    if (tileInfo) {
      selectedInfos.push(tileInfo);
      continue;
    }

    var itemInfo = getItemInfoFromValue(item.value);
    if (itemInfo) {
      selectedInfos.push(itemInfo);
      continue;
    }

    var wallInfo = getWallInfoFromValue(item.value);
    if (wallInfo) {
      selectedInfos.push(wallInfo);
    }
  }

  return selectedInfos;
}

function getTileInfoFrom(id, u, v) {
  var tileInfo = settings.Tiles[id];

  if (tileInfo && tileInfo.Frames) {
    for (var frameIndex = 0; frameIndex < tileInfo.Frames.length; frameIndex++) {
      var frame = tileInfo.Frames[frameIndex];

      if (u != frame.U) continue;
      if (v != frame.V) continue;

      frame.parent = tileInfo;
      return frame;
    }
  }

  return tileInfo;
}

function getItemInfoFromValue(value) {
  if (typeof value !== 'string' || value.indexOf('item') !== 0) return null;

  for (var i = 0; i < settings.Items.length; i++) {
    var item = settings.Items[i];
    if (value === 'item' + item.Id) {
      return item;
    }
  }
  return null;
}

function getWallInfoFromValue(value) {
  if (typeof value !== 'string' || value.indexOf('wall') !== 0) return null;

  for (var i = 0; i < settings.Walls.length; i++) {
    var wall = settings.Walls[i];
    if (value === 'wall' + wall.Id) {
      return wall;
    }
  }
  return null;
}

/* ================================================================
 *  Tile 信息获取（保留原有逻辑）
 * ================================================================ */
function getTileInfo(tile) {
  var tileInfo = settings.Tiles[tile.Type];
  if (!tileInfo) return tileInfo;
  if (!tileInfo.Frames) return tileInfo;

  var matchingFrame;

  for (var i = 0; i < tileInfo.Frames.length; i++) {
    var frame = tileInfo.Frames[i];

    if ((!frame.U && !tile.TextureU) || frame.U <= tile.TextureU) {
      if ((!frame.V && !tile.TextureV) || frame.V <= tile.TextureV)
        matchingFrame = frame;
    }
  }

  if (!matchingFrame) return tileInfo;

  matchingFrame.parent = tileInfo;
  return matchingFrame;
}

/* ================================================================
 *  清除 / 重置
 * ================================================================ */
function clearHighlight() {
  overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  selectionCtx.clearRect(0, 0, selectionCanvas.width, selectionCanvas.height);
}

function clearSelection() {
  selectionCtx.clearRect(0, 0, selectionCanvas.width, selectionCanvas.height);
}

function resetPanZoom(e) {
  panzoom.panzoom('reset');
}

function resizeCanvases() {
  var width = window.innerWidth * 0.99;
  var ratio = panzoomContainer.height / panzoomContainer.width;
  var height = width * ratio;

  panzoomContainer.style.width = width + 'px';
  panzoomContainer.style.height = height + 'px';
  canvas.style.width = width + 'px';
  overlayCanvas.style.width = width + 'px';
  selectionCanvas.style.width = width + 'px';
  $('#canvasContainer').css("overflow", "visible");
}

/* ================================================================
 *  鼠标交互
 * ================================================================ */
function getMousePos(canvas, evt) {
  var rect = panzoomContainer.getBoundingClientRect();
  var scale = rect.width / panzoomContainer.width;

  return {
    x: Math.floor((evt.clientX - rect.left) / scale),
    y: Math.floor((evt.clientY - rect.top) / scale)
  };
}

function getItemText(item) {
  var prefix = "";

  if (item.prefixId > 0 && item.prefixId < settings.ItemPrefix.length)
    prefix = settings.ItemPrefix[item.prefixId].Name;

  var itemName = item.id;
  for (var itemIndex = 0; itemIndex < settings.Items.length; itemIndex++) {
    var itemSettings = settings.Items[itemIndex];
    if (Number(itemSettings.Id) === item.id) {
      itemName = itemSettings.Name;
      break;
    }
  }
  return prefix + ' ' + itemName + ' (' + item.count + ')';
}

panzoomContainer.addEventListener('mousemove', function (evt) {
  if (!world) return;

  var mousePos = getMousePos(panzoomContainer, evt);

  $("#status").html(mousePos.x + ',' + mousePos.y);

  if (world.tiles) {
    var tile = getTileAt(mousePos.x, mousePos.y);
    if (tile) {
      var text = getTileText(tile);
      $("#status").html(text + ' (' + mousePos.x + ', ' + mousePos.y + ')');
    }
  }
});

$("#panzoomContainer").on('panzoomend', function (evt, panzoom, matrix, changed) {
  if (changed) return;

  var mousePos = getMousePos(panzoomContainer, evt);
  selectionX = mousePos.x;
  selectionY = mousePos.y;

  drawSelectionIndicator();

  var tile = getTileAt(mousePos.x, mousePos.y);
  if (tile) {
    var text = getTileText(tile);

    $("#tileInfoList").html("");

    var chest = tile.chest;
    if (chest) {
      if (chest.name.length > 0) text = text + ' - ' + chest.name;

      for (var i = 0; i < chest.items.length; i++) {
        var item = chest.items[i];
        var itemText = getItemText(item);
        $("#tileInfoList").append('<li>' + itemText + '</li>');
      }
    }

    var tileEntity = tile.tileEntity;
    if (tileEntity) {
      switch (tileEntity.type) {
        case 3:
        case 5:
          var items = tileEntity.items;
          var dyes = tileEntity.dyes;
          for (var i = 0; i < items.length; i++) {
            if (items[i].id > 0) {
              $("#tileInfoList").append('<li>' + getItemText(items[i]) + '</li>');
            }
            if (dyes[i].id > 0) {
              $("#tileInfoList").append('<li>' + getItemText(dyes[i]) + '</li>');
            }
          }
          break;
      }
    }

    var sign = tile.sign;
    if (sign && sign.text && sign.text.length > 0) {
      $("#tileInfoList").append('<li>' + sign.text + '</li>');
    }

    $("#tile").html(text);
  }
});

function getTileAt(x, y) {
  if (!world) return;
  var index = x * world.height + y;
  if (index >= 0 && index < world.tiles.length) {
    return world.tiles[index];
  }
  return null;
}

function selectPoint(x, y) {
  selectionX = x;
  selectionY = y;
  drawSelectionIndicator();
}

function drawSelectionIndicator() {
  var x = selectionX + 0.5;
  var y = selectionY + 0.5;

  var lineWidth = 12;
  var targetWidth = 39;
  var halfTargetWidth = targetWidth / 2;

  selectionCtx.clearRect(0, 0, selectionCanvas.width, selectionCanvas.height);
  selectionCtx.lineWidth = lineWidth;
  selectionCtx.strokeStyle = "rgb(255, 0, 0)";
  selectionCtx.strokeRect(x - halfTargetWidth, y - halfTargetWidth, targetWidth, targetWidth);

  selectionCtx.lineWidth = 1;
  selectionCtx.beginPath();
  selectionCtx.moveTo(x - halfTargetWidth, y);
  selectionCtx.lineTo(x - 1, y);
  selectionCtx.stroke();
  selectionCtx.beginPath();
  selectionCtx.moveTo(x + halfTargetWidth, y);
  selectionCtx.lineTo(x + 1, y);
  selectionCtx.stroke();
  selectionCtx.beginPath();
  selectionCtx.moveTo(x, y - halfTargetWidth);
  selectionCtx.lineTo(x, y - 1);
  selectionCtx.stroke();
  selectionCtx.beginPath();
  selectionCtx.moveTo(x, y + halfTargetWidth);
  selectionCtx.lineTo(x, y + 1);
  selectionCtx.stroke();
}

/* ================================================================
 *  Tile 文本描述
 * ================================================================ */
function getTileText(tile) {
  var text = "虚无";

  if (!tile) return text;

  var tileInfo = tile.info;

  if (tileInfo) {
    if (!tileInfo.parent || !tileInfo.parent.Name) {
      text = tileInfo.Name;
    } else if (tileInfo.parent && tileInfo.parent.Name) {
      text = tileInfo.parent.Name;

      if (tileInfo.Name) {
        text = text + ' - ' + tileInfo.Name;
        if (tileInfo.Variety)
          text = text + ' - ' + tileInfo.Variety;
      } else if (tileInfo.Variety) {
        text = text + ' - ' + tileInfo.Variety;
      }
    }

    if (tile.TextureU > 0 && tile.TextureV > 0)
      text = text + ' (' + tile.Type + ', ' + tile.TextureU + ', ' + tile.TextureV + ')';
    else if (tile.TextureU > 0)
      text = text + ' (' + tile.Type + ', ' + tile.TextureU + ')';
    else
      text = text + ' (' + tile.Type + ')';

    if (tile.tileEntity) {
      var tileEntity = tile.tileEntity;
      switch (tileEntity.type) {
        case 1:
        case 4:
        case 6:
          var entityItem = tileEntity.item;
          text = text + ' - ' + getItemText(entityItem);
          break;
        case 2:
          var checkType = tile.info.CheckTypes[tileEntity.logicCheckType];
          var on = tileEntity.on ? "On" : "Off";
          text = text + ' - ' + checkType + ', ' + on;
          break;
      }
    }
  } else if (tile.WallType || tile.WallType === 0) {
    if (tile.WallType < settings.Walls.length) {
      text = settings.Walls[tile.WallType].Name + ' (' + tile.WallType + ')';
    } else {
      text = 'Unknown Wall (' + tile.WallType + ')';
    }
  }

  if (tile.IsLiquidPresent) {
    if (text === "Nothing") text = "";

    if (tile.IsLiquidLava) text += text ? " Lava" : "Lava";
    else if (tile.IsLiquidHoney) text += text ? " Honey" : "Honey";
    else if (tile.Shimmer) text += text ? " Shimmer" : "Shimmer";
    else text += text ? " Water" : "Water";
  }

  if (tile.IsRedWirePresent) text += " (Red Wire)";
  if (tile.IsGreenWirePresent) text += " (Green Wire)";
  if (tile.IsBlueWirePresent) text += " (Blue Wire)";
  if (tile.IsYellowWirePresent) text += " (Yellow Wire)";

  return text;
}

/* ================================================================
 *  文件加载
 * ================================================================ */
function fileNameChanged(evt) {
  file = evt.target.files[0];
  $("#help").hide();
  reloadWorld();
}

function reloadWorld() {
  var worker = new Worker('resources/js/WorldLoader.js');
  worker.addEventListener('message', onWorldLoaderWorkerMessage);
  worker.postMessage(file);
}

function onWorldLoaderWorkerMessage(e) {
  if (e.data.status) $("#status").html(e.data.status);

  if (e.data.tiles) {
    var bufferWidth = 200;
    if (!pixels) {
      pixels = new Uint8ClampedArray(4 * bufferWidth * world.height);
    }
    var xlimit = e.data.x + e.data.tiles.length / world.height;
    var i = 0;
    for (var x = e.data.x; x < xlimit; x++) {
      var bufferStart = bufferWidth * Math.floor(x / bufferWidth);
      if (x % bufferWidth === 0 && x > 0) {
        var imageData = new ImageData(pixels, bufferWidth);
        ctx.putImageData(imageData, bufferStart - bufferWidth, 0);
      }
      for (var y = 0; y < world.height; y++) {
        var tile = e.data.tiles[i++];
        if (tile) {
          tile.info = getTileInfo(tile);
          world.tiles.push(tile);

          var c = getTileColor(y, tile, world);
          if (!c) c = { "r": 0, "g": 0, "b": 0 };

          var pxIdx = 4 * (y * bufferWidth + x - bufferStart);
          pixels[pxIdx] = c.r;
          pixels[pxIdx + 1] = c.g;
          pixels[pxIdx + 2] = c.b;
          pixels[pxIdx + 3] = 255;
        }
      }
    }
  }

  if (e.data.done) {
    var bufferWidth = 200;
    var bufferStart = bufferWidth * Math.floor((world.width - 1) / bufferWidth);
    var imageData = new ImageData(pixels, bufferWidth);
    ctx.putImageData(imageData, bufferStart, 0);
    pixels = null;
  }

  if (e.data.chests) {
    world.chests = e.data.chests;

    for (var i = 0; i < e.data.chests.length; i++) {
      var chest = e.data.chests[i];
      var idx = chest.x * world.height + chest.y;
      world.tiles[idx].chest = chest;
      world.tiles[idx + 1].chest = chest;

      idx = (chest.x + 1) * world.height + chest.y;
      world.tiles[idx].chest = chest;
      world.tiles[idx + 1].chest = chest;
    }
  }

  if (e.data.signs) {
    world.signs = e.data.signs;

    for (var i = 0; i < e.data.signs.length; i++) {
      var sign = e.data.signs[i];
      var tileIndex = sign.x * world.height + sign.y;
      world.tiles[tileIndex].sign = sign;
      world.tiles[tileIndex + 1].sign = sign;

      tileIndex = (sign.x + 1) * world.height + sign.y;
      world.tiles[tileIndex].sign = sign;
      world.tiles[tileIndex + 1].sign = sign;
    }
  }

  if (e.data.npcs) {
    addNpcs(e.data.npcs);
  }

  if (e.data.tileEntities) {
    for (var entry of e.data.tileEntities.entries()) {
      var pos = entry[0];
      var entity = entry[1];
      var idx = pos.x * world.height + pos.y;
      var tile = world.tiles[idx];
      if (tile) {
        var size = tile.info.Size;
        var sizeX = 1;
        var sizeY = 1;
        if (size) {
          sizeX = size[0] - '0';
          sizeY = size[2] - '0';
        }
        for (var sx = 0; sx < sizeX; sx++) {
          for (var sy = 0; sy < sizeY; sy++) {
            var tileIdx = (pos.x + sx) * world.height + pos.y + sy;
            world.tiles[tileIdx].tileEntity = entity;
          }
        }
      }
    }
  }

  if (e.data.world) {
    world = e.data.world;

    panzoomContainer.width = world.width;
    panzoomContainer.height = world.height;
    canvas.width = world.width;
    canvas.height = world.height;
    overlayCanvas.width = world.width;
    overlayCanvas.height = world.height;
    selectionCanvas.width = world.width;
    selectionCanvas.height = world.height;

    world.tiles = [];

    resizeCanvases();

    $("#worldPropertyList").empty();

    Object.keys(world).filter(function (key) {
      var value = world[key];
      var type = typeof value;
      return type === 'string' || type === 'number' || type === 'boolean' || type === 'bigint';
    }).sort()
      .forEach(function (key) {
        $("#worldPropertyList").append('<li>' + key + ': ' + world[key] + '</li>');
      });
  }
}

function addNpcs(npcs) {
  world.npcs = npcs;

  for (var i = 0; i < npcs.length; i++) {
    var npc = npcs[i];

    var npcText = npc.name;
    if (npc.type != npc.name) {
      npcText = npcText + ' the ' + npc.type;
    }

    $("#npcList").append('<li><a href="#" onclick="selectPoint(' + npc.x + ', ' + npc.y + ')">' + npcText + '</a></li>');
  }
}

function getTileColor(y, tile, world) {
  if (tile.IsActive) {
    return tileColors[tile.Type][0];
  }

  if (tile.IsLiquidPresent) {
    if (tile.IsLiquidLava) return liquidColors[1];
    else if (tile.IsLiquidHoney) return liquidColors[2];
    else if (tile.Shimmer) return liquidColors[3];
    else return liquidColors[0];
  }

  if (tile.IsWallPresent) {
    var color = wallColors[tile.WallType][0];
    if (!color || (color.r === 0 && color.g === 0 && color.b === 0)) {
      var wall = settings.Walls.find(function (w) { return w.Id === tile.WallType.toString(); });
      if (wall && wall.Color) return wall.Color;
    }
    return color;
  }

  if (y < world.worldSurfaceY) return { "r": 132, "g": 170, "b": 248 };
  if (y < world.rockLayerY) return { "r": 88, "g": 61, "b": 46 };
  if (y < world.hellLayerY) return { "r": 74, "g": 67, "b": 60 };

  return { "r": 0, "g": 0, "b": 0 };
}

function saveMapImage() {
  var newCanvas = document.createElement("canvas");
  var newContext = newCanvas.getContext("2d");

  newCanvas.height = world.height;
  newCanvas.width = world.width;

  newContext.drawImage(canvas, 0, 0);
  newContext.drawImage(overlayCanvas, 0, 0);
  newContext.drawImage(selectionCanvas, 0, 0);

  newCanvas.toBlob(function (blob) {
    saveAs(blob, world.name + '.png');
  });
}