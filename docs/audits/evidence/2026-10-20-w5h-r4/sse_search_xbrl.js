$('.linkbar a').each(function () {
  $(this).attr('href', 'javascript:void(0);');
})
var js_source = $('.js_source');

function source(name) {
  if (js_source.length) {
    js_source.html('Source：' + (iscompare ? ($('.search_contentpc .js_year').val() + ' - ' + _translate[reporttype.val()]) : (name + ' - ' + _translate[reporttype.val()])) + ' (XBRL Report)');
  }
}

var reporttype = $('.js_reporttype'),
  urlcode = /^(\d{6}[,]{0,1})*(\d{6})$/;
_translate = {
  '5000': 'Annual report',
  '4000': 'Quarterly report',
  '1000': 'Semi-annual report',
  '4400': 'Three quarterly report'
};

// 查询框逻辑
var globalMethods = {
  globalSearch: function () {
    var code = $.trim($("#inputCode").val());
    if (globalMethods.getCode(code)) {
      if (globalMethods.codeCheck(code)) {
        var ipoData = get_data();
        for (var i = 0; i < ipoData.length; i++) {
          if (ipoData[i].val == code || ipoData[i].val2 == code) {
            var code = ipoData[i].val
          }
        }
        var reportId = $('.js_reporttype').val()
        window.location.href = '/markets/dataservice/xbrl/companyinfo/?stock_id=' + code + '&report_period_id=' + reportId;
      }
    }
  },
  getCode: function (code) {
    var reg_num = /^[\d]+$/;
    var reg_one = /^([0-9]{6})$/;
    var reg_text = /^[\u4E00-\u9FA5A-Za-z0-9]+$/;
    var code = $.trim(code);
    if (code.length > 6 || code.length == 0) {
      alert("Please enter six correct stock codes.")
      return false;
    } else {
      if (reg_num.test(code)) {
        if (!reg_one.test(code)) {
          alert("Please enter six correct stock codes.")
          return false;
        } else {
          return true;
        }
      } else {
        if (!reg_text.test(code)) {
          alert("Please enter six correct stock codes.")
          return false;
        } else {
          return true;
        }

      }
    }
  },
  codeCheck: function (code) {
    var ipoData = get_data();
    if (ipoData != null && ipoData.length > 0) {
      var exist = false;
      for (var i = 0; i < ipoData.length; i++) {
        if (ipoData[i].val == code || ipoData[i].val2 == code) {
          exist = true;
          var code = ipoData[i].val
          break;
        }
      }
      if (!exist) {
        alert("Please enter six correct stock codes.");
        return false;
      }
    } else {
      alert("Please enter six correct stock codes.");
      return false;
    }
    return true;
  }
};


function floatfommatter(num, zd) {
  var reg_1 = /^\d+(\.\d+)?$/; //非负浮点数
  var reg_2 = /^(-(([0-9]*\.[0-9]*[1-9][0-9]*)|([0-9]*[1-9][0-9]*\.[0-9]+)|([0-9]*[1-9][0-9]*)))$/;
  var reg_3 = /S1010_0010|S1010_0220|S1010_0170|S1010_0200|S1010_0230|S1010_0250|S1010_0270|S1080_0010|S1050_0030|S1050_0040|S2020_0330|S2020_0340/;
  if (zd.substring(0, 10) == 'S1050_0040') {
    return num + '%';
  } else if ((reg_1.test($.trim(num)) || reg_2.test($.trim(num))) && zd != 'S1010_0190') {
    return toThousands($.trim((reg_3.test(zd)) == true ? num : num));
  } else {
    return num;
  }
}
var report_period_id = getValue('report_period_id'),
  stock_id = getValue('stock_id') || '600009',
  iscompare = getValue('iscompare') || false,
  typeoption = [];

//判断是否是行业对比
!iscompare ? $('.js_year').parents('.input_block').hide() : $('.js_equities_ia').parents('.input_block').hide();
if (stock_id) {
  $('.search_contentmobile #inputCode').val(stock_id);
  $('.search_contentpc #inputCode').val(stock_id);
}

if (reporttype.length && $('.js_xbrl_list').length > 0) {
  var periodIdSelect = [
    ['5000,1000', 'ALL'],
    ['5000', 'Annual report'],
    ['1000', 'Semi-annual report'],
  ]
  $(periodIdSelect).each(function (i, select) {
    typeoption.push('<option value="' + select[0] + '" ' + (i == 0 ? 'selected="selected"' : '') + '>' + select[1] + '</option>');
  })
  reporttype.html(typeoption.join('')); //类型渲染
  require(["multipleSelect"], function () { //渲染下拉框
    multipleSelec('.js_reporttype');
  });
} else {
  if (reporttype.length) {
    // sse_setCookie('js_equities_ia', code);//保存查询历史
    var periodIdSelect = [
      ['5000', 'Annual report'],
      ['4000', 'Quarterly report'],
      ['1000', 'Semi-annual report'],
      ['4400', 'Three quarterly report']
    ]
    $(periodIdSelect).each(function (i, select) {
      typeoption.push('<option value="' + select[0] + '" ' + (/4400|1000|5000|4000/g.test(report_period_id) ? (report_period_id == select[0] ? 'selected="selected"' : '') : (i == 0 ? 'selected="selected"' : '')) + '>' + select[1] + '</option>');
    })
  
    reporttype.html(typeoption.join('')); //市场渲染
    require(["multipleSelect"], function () { //渲染下拉框
      multipleSelec('.js_reporttype');
    });
  }
}

var jsyear = $('.js_year');
if (jsyear.length) {
  var _year = Number(get_systemDate_global().substring(0, 4)),
    years = [];
  for (var i = _year; i > _year - 5; i--) {
    years.push('<option value="' + i + '" ' + (i == (_year - 1) ? 'selected="selected"' : '') + '>' + i + '</option>');
  }
  jsyear.html(years.join(''));
  require(["multipleSelect"], function () { //渲染下拉框
    multipleSelec('.js_year');
  });
}

var xbrllist = $('.js_xbrl_list');
if (xbrllist.length) { //公司列表
  var pageSize = 25;
  var xbrlObj = {
    url: sseQueryURL + 'commonSoaQuery.do',
    datas: {
      isPagination: true,
      sqlId: 'COMMON_SSE_PL_XBRL_YJGL',
      stockId:'',
      startYear:'',
      endYear:'',
      reportPeriodId:'5000,1000',
      type:'inParams',
      isMax:'1',
      'pageHelp.pageSize':pageSize,
      'pageHelp.pageNo':'1',
      'pageHelp.beginPage': '1',
      'pageHelp.cacheSize': '1',
      'pageHelp.endPage': '1'
    }
  };
  //数据渲染
  function selectDatas(){
    xbrlObj.datas.isMax = (isNaN(xbrlObj.datas.startYear) && isNull(xbrlObj.datas.endYear)) ? '1' : ''; //是否取最大值
    xbrlObj.datas.stockId = $('#inputCode').val(); //公司代码
    var res = /^\d{6}$/;
    if (xbrlObj.datas.stockId && !res.test(xbrlObj.datas.stockId)) {
      alert("Please enter six correct stock codes.");
      return;
    }
    xbrlObj.datas.reportPeriodId = $('.js_reporttype').val(); //报告类型
    
    var str1 = $('.js_year_start').val();
    var str2 = $('.js_year_end').val();
    if(str1 > str2){
      alert("The start year cannot be longer than the end year.");
      return  false;
    }
    if(str1 == str2){
      xbrlObj.datas.startYear = str1;//开始年份
      xbrlObj.datas.endYear = str1;//结束年份
    } else {
      xbrlObj.datas.startYear = str1;//开始年份
      xbrlObj.datas.endYear = str2;//结束年份
    }

    showCompanyAnnouncements(1); //渲染数据
  }
  var getDatas = function getData(res) {
    var htmlArr = [];
    var resultData = res.result
    htmlArr.push('<thead><tr><th>Code</th><th>Short Name</th><th>Report Type</th><th>Date of Disclosure</th></tr></thead><tbody>');
    if (resultData && resultData.length > 0) {
      if(xbrlObj.datas.isMax == '1'){
        $('.js_year_start').val(resultData[0].REPORT_YEAR);
        $('.js_year_end').val(resultData[0].REPORT_YEAR);
      }
      $(resultData).each(function (i, obj) {
        htmlArr.push('<tr><td><div class="nowrap"><a href="/markets/dataservice/cpd/cinfo/index.shtml?COMPANY_CODE=' + obj.STOCK_ID + '&REPORT_YEAR=' + obj.REPORT_YEAR + '&REPORT_PERIOD_ID=' + obj.REPORT_PERIOD_ID + '&COMPANY_ABBR=' + obj.COMPANY_ABBR + '" target="_blank">' + obj.STOCK_ID + '</a></div></td>');
        if (obj.COMPANY_ABBR == '-' || $.trim(obj.COMPANY_ABBR) == '') {
          htmlArr.push('<td>-</td>');
        } else {
          htmlArr.push('<td><div class="nowrap"><a href="/markets/dataservice/cpd/cinfo/index.shtml?COMPANY_CODE=' + obj.STOCK_ID + '&REPORT_YEAR=' + obj.REPORT_YEAR + '&REPORT_PERIOD_ID=' + obj.REPORT_PERIOD_ID + '&COMPANY_ABBR=' + obj.COMPANY_ABBR + '" target="_blank">' + obj.COMPANY_ABBR + '</a></div></td>');
        }
        htmlArr.push('<td><div class="nowrap"><a href="/markets/dataservice/cpd/cinfo/index.shtml?COMPANY_CODE=' + obj.STOCK_ID + '&REPORT_YEAR=' + obj.REPORT_YEAR + '&REPORT_PERIOD_ID=' + obj.REPORT_PERIOD_ID + '&COMPANY_ABBR=' + obj.COMPANY_ABBR + '" target="_blank">'  + (_translate[obj.REPORT_PERIOD_ID] + ' ('+ obj.REPORT_YEAR +')' || '') + '</a></div></td>');
        htmlArr.push('<td>' + obj.ACTUAL_DATE + '</td></tr>');
      })
    } else {
      htmlArr.push('<tr><td colspan="4">No Data Available!</td></tr>');
      htmlArr.push('</tbody>');
      xbrllist.html(htmlArr.join(''));
      $('.pagination').parent().hide();
      hideloading();
      return;
    }
    htmlArr.push('</tbody>');
    xbrllist.html(htmlArr.join(''));
    var totalPage = (res.pageHelp.total % pageSize == 0 ? parseInt(res.pageHelp.total / pageSize) : (parseInt(res.pageHelp.total / pageSize) + 1));
    if (totalPage > 1) {
        Page.navigation('.pagination', totalPage, xbrlObj.datas['pageHelp.pageNo'], "showCompanyAnnouncements");
        Page.phonenavigation('.mobile-page', totalPage, xbrlObj.datas['pageHelp.pageNo'], 'showCompanyAnnouncements');
        $('.pagination').parent().show();
    } else {
      $('.pagination').parent().hide();
    }
    hideloading();
  }

  showCompanyAnnouncements(xbrlObj.datas['pageHelp.pageNo']);

  function showCompanyAnnouncements(page) {
      showloading();
      page = Page.check(page, 'showCompanyAnnouncements');
      if (page != null) {
        xbrlObj.datas['pageHelp.pageNo'] = page;
          ajaxFun(xbrlObj, getDatas);
      }
  }

  $('#btnQuery').click(function () {
    selectDatas();
  })
  $('#btnReset').click(function () {
    window.location.reload();
  })
  // 查询框默认code
  var codeValue = getValue('stock_id').replace('.SS', '');
  codeValue ? $("#inputCode").val(codeValue) : '';
}

function leftclick() { //详情页面左侧搜索框
  var _slider = $('.slider_search_block');
  if (_slider.hasClass('slider_search_close') == false) {
    _slider.addClass('slider_search_close').removeClass('slider_search_open');
  } else {
    _slider.css('display', 'block').addClass('slider_search_open').removeClass('slider_search_close');
  }
}

$('.sse_en_iconsearch-style').on('click', function () {
  leftclick();
})


$(document).click(function (e) {
  var target = $(e.target);
  if (target.closest(".slider_search_block").length == 0 && target.closest(".sse_en_iconsearch-style").length == 0) {
    $('.slider_search_block').addClass('slider_search_close').removeClass('slider_search_open');
    setTimeout(function () {
      $('.slider_search_block').css('display', 'none');
      $('.mainbg').removeClass('slider_search');
    }, 500);
  }
})

var doc = $(document),
  bh = $('.js_page_banner').height(),
  navh = $('.js_nav-pc').height(),
  ss_top = 268;

function _left() { //控制左侧搜索框显示位置
  var _top = doc.scrollTop();
  if (_top >= bh) {
    $('.slider_search_block').css('top', navh + 2);
  } else {
    $('.slider_search_block').css('top', ss_top - _top);
  }
}
_left();
$(window).scroll(function () {
  _left();
});

function _showTableData(leftcolumns, datas) { //拼装table表格
  datas = leftcolumns.fommatter(datas);
  // source(infoObj.companies[stock_id]);
  source(stock_id);
  var htmlStr = []
  $(leftcolumns.rowname).each(function (i, rname) {
    if (i == 0) {
      htmlStr.push('<thead><tr><th style="min-width:160px;" >' + (iscompare ? ($('#js_topten.active').length > 0 ? 'Ranking/Short Name' : 'Indicator/Short Name') : rname[0]) + '</th>');
      $(infoObj.yearList).each(function (j, cols) {
        htmlStr.push('<th style="min-width:160px;">' + (iscompare ? '<a href="/markets/dataservice/xbrl/companyinfo/?stock_id=' + cols + '&report_period_id=' + reporttype.val() + '">' + infoObj.companies[cols] + '</a>' : cols) + '</th>');
      })
      htmlStr.push('</tr></thead>');
    } else {
      htmlStr.push(i == 1 ? '<tbody>' : '');

      if(/^(1|2|3|4|5|6|7|8|9|10)$/g.test(rname[0])){
        htmlStr.push('<tr><td>' + rname[0] + '</td>');
      } else {
        htmlStr.push('<tr><td><div class="align_left">' + rname[0] + '</div></td>');
      }
      $(datas).each(function (j, cols) {
        htmlStr.push('<td>');

        var htmlArr = [],
          len = false;
        for (var i = 1; i < rname.length; i++) {
          htmlArr.push((cols[rname[i]] ? (leftcolumns.prefix[i - 1] + floatfommatter(cols[rname[i]], rname[i])) : '') + (i < rname.length - 1 ? '<br/>' : ''));
          if (/^S1050_00/g.test(rname[i])) {
            len = true;
          }
        }
        if (len) {
          htmlStr.push('<div class="align_left">' + htmlArr.join('') + '</div>')
        } else {
          htmlStr.push(htmlArr.join(''));
        }

        htmlStr.push('</td>');
      })
      htmlStr.push('</tr>');
      htmlStr.push(leftcolumns.rowname.length == (i + 1) ? '</tbody>' : '');
    }
  })
  return htmlStr.join('');
}

var xbrlinfo = $('.js_xbrl_info');
if (xbrlinfo.length) {
  var infoObj = {
    js_binfo: {
      chinese: '基本信息',
      prefix: [''],
      rowname: [
        ['Indicator/Year', 'REPORT_YEAR'],
        ['Company Name', 'S1010_0010'], //S1010_0030
        ['Legal representative', 'S1010_0220'],
        ['Address of registrant', 'S1010_0170'],
        ['Postal code of the office address', 'S1010_0190'],
        ['Businss website', 'S1010_0200'],
        ['Name of company secretary', 'S1010_0230'],
        ['Telephone number of company secretary', 'S1010_0250'],
        ['E-mail address of company secretary', 'S1010_0270'],
        ['Total shareholders at the end of the reporting period', 'S1080_0010'],
        ['Number of bonus shares for every 10 shares', 'S5010_0020'],
        ['Dividends per 10 shares (tax included)', 'S5010_0030'],
        ['Number of shares converted from reserve capital per 10 shares', 'S5010_0040'],
        ['Operating income for the perid (yuan)', 'S2090_0010'],
        ['Operating profit for the period (yuan)', 'S2090_0020'],
        ['Gross profit (yuan)', 'S2090_0030'],
        ['Net profit attributable to shareholders (yuan)', 'S2090_0040'],
        ['Net profit attributable to shareholders after deducting non-recurring gains and losses (yuan)', 'S2090_0050'],
        ['Net cash provided by operating activities (yuan)', 'S2090_0060'],
        ['Total assets (yuan)', 'S2090_0070'],
        ['Shareholders\' equity (yuan)', 'S2090_0080'],
        ['Basic earnings per share (yuan/share)', 'S2090_0090'],
        ['Diluted earnings per share (yuan/share)', 'S2090_0100'],
        ['Basic earnings per share after deducting non-recurring gains and losses (yuan/share)', 'S2090_0110'],
        ['Fully diluted return on net assets (%)', 'S2090_0120'],
        ['Weighted average return on net assets (%)', 'S2090_0130'],
        ['Fully diluted return on net assets after deducting non-recurring gains and losses (%)', 'S2090_0140'],
        ['Weighted average return on net assets after deducting non-recurring gains and losses (%)', 'S2090_0150'],
        ['Net cash provided by operating activities per share (yuan/share)', 'S2090_0160'],
        ['Net assets attributable to shareholders per share (yuan/share)', 'S2090_0170']
      ],
      sqlid: 'COMMON_MAP_BASIC_COMPANYINFO_C',
      fommatter: function () {
        var datas = arguments[0],
          result = [];
        var obj = infoObj.yearObj();
        if (datas && datas.length > 0) {
          for (var i = 0; i < datas.length; i++) {
            var data = datas[i];
            obj[iscompare ? data.STOCK_ID.replace('.SS', '') : data.REPORT_YEAR].push(data);
          }
        }

        var _obj = [],
          j = 0;
        $(Object.keys(obj)).each(function (i, k) {
          _obj[i] = obj[k];
        })

        for (var i = _obj.length - 1; i >= 0; i--) {
          result[j] = result[j] || {};
          $(_obj[i]).each(function (i, o) {
            result[j] = o;
          })
          j++;
        }
        return result;
      }
    },
    js_topten: {
      chinese: '前10大股东',
      prefix: ['Name:', 'Number of shares:', 'Shareholding ratio:'],
      rowname: [
        ['Ranking/Year', 'REPORT_YEAR'],
        ['1', 'S1050_0010_0', 'S1050_0030_0', 'S1050_0040_0'],
        ['2', 'S1050_0010_1', 'S1050_0030_1', 'S1050_0040_1'],
        ['3', 'S1050_0010_2', 'S1050_0030_2', 'S1050_0040_2'],
        ['4', 'S1050_0010_3', 'S1050_0030_3', 'S1050_0040_3'],
        ['5', 'S1050_0010_4', 'S1050_0030_4', 'S1050_0040_4'],
        ['6', 'S1050_0010_5', 'S1050_0030_5', 'S1050_0040_5'],
        ['7', 'S1050_0010_6', 'S1050_0030_6', 'S1050_0040_6'],
        ['8', 'S1050_0010_7', 'S1050_0030_7', 'S1050_0040_7'],
        ['9', 'S1050_0010_8', 'S1050_0030_8', 'S1050_0040_8'],
        ['10', 'S1050_0010_9', 'S1050_0030_9', 'S1050_0040_9']
      ],
      sqlid: 'COMMON_MAP_TOP10_C',
      fommatter: function () {
        var datas = arguments[0],
          result = [];
        var obj = infoObj.yearObj();
        if (datas && datas.length > 0) {
          for (var i = 0; i < datas.length; i++) {
            var data = datas[i];
            obj[iscompare ? data.STOCK_ID.replace('.SS', '') : data.REPORT_YEAR].push(data);
          }
        }
        var _obj = [],
          j = 0;
        $(Object.keys(obj)).each(function (i, k) {
          _obj[i] = obj[k];
        })
        for (var i = _obj.length - 1; i >= 0; i--) {
          result[j] = result[j] || {};
          $(_obj[i]).each(function (i, o) {
            result[j]['REPORT_YEAR'] = o.REPORT_YEAR;
            result[j]['S1050_0010_' + i] = o.S1050_0010;
            result[j]['S1050_0030_' + i] = o.S1050_0030;
            result[j]['S1050_0040_' + i] = o.S1050_0040;
          })
          j++

        }
        return result;
      }
    },
    js_scs: {
      chinese: '股本结构',
      prefix: [''],
      rowname: [
        ['Indicator/Year', 'REPORT_YEAR'],
        ['Number of state-owned restricted shares', 'S1040_0020_8'],
        ['Number of restricted shares held by state-owned legal persons', 'S1040_0030_8'],
        ['Number of other domestically-held outstanding restricted shares', 'S1040_0040_8'],
        ['Number of restricted shares held by domestic legal persons', 'S1040_0050_8'],
        ['Number of outstanding restricted shares held by domestic natural persons', 'S1040_0060_8'],
        ['Number of foreign -held outstanding restricted shares', 'S1040_0070_8'],
        ['Number of outstanding restricted shares held by foreign legal persons', 'S1040_0080_8'],
        ['Number of outstanding restricted shares  held by foreign natural persons', 'S1040_0090_8'],
        ['Number of other outstanding restricted shares', 'S1040_0100_8'],
        ['Number of total outstanding restricted shares', 'S1040_0010_8'],
        ['Number of RMB common shares with no sale restrictions', 'S1040_0120_8'],
        ['Number of domestically-listed and foreign-held shares with no sale restrictions', 'S1040_0130_8'],
        ['Number of foreign-listed and foreign-held shares with no sale restrictions', 'S1040_0140_8'],
        ['Number of other outstanding shares with no sale restrictions', 'S1040_0150_8'],
        ['Total outstanding shares with no sale restrictions', 'S1040_0110_8'],
        ['Total shares', 'S1040_0160_8'],
        ['Proportion of state-owned restricted shares in the total share capital (%)', 'S1040_0020_9'],
        ['Proportion of restricted shares held by state-owned legal persons in the total share capital (%)', 'S1040_0030_9'],
        ['Proportion of other domestically-held outstanding restricted shares in the total share capital (%)', 'S1040_0040_9'],
        ['Proportion of restricted shares held by state-owned legal persons in the total share capital (%)', 'S1040_0050_9'],
        ['Proportion of outstanding restricted shares held by domestic natural persons in the total share capital (%)', 'S1040_0060_9'],
        ['Proportion of foreign -held outstanding restricted shares in the total share capital (%)', 'S1040_0070_9'],
        ['Proportion of outstanding restricted shares held by foreign legal persons in the total share capital (%)', 'S1040_0080_9'],
        ['Proportion of outstanding restricted shares  held by foreign natural persons in the total share capital (%)', 'S1040_0090_9'],
        ['Proportion of other outstanding restricted shares in the total share capital (%)', 'S1040_0100_9'],
        ['Proportion of total outstanding restricted shares in the total share capital (%)', 'S1040_0010_9'],
        ['Proportion of RMB common shares with no sale restrictions in the total share capital (%)', 'S1040_0120_9'],
        ['Proportion of domestically-listed and foreign-held shares with no sale restrictions in the total share capital (%)', 'S1040_0130_9'],
        ['Proportion of foreign-listed and foreign-held shares with no sale restrictions in the total share capital (%)', 'S1040_0140_9'],
        ['Proportion of other outstanding shares with no sale restrictions in the total share capital (%)', 'S1040_0150_9'],
        ['Proportion of total outstanding shares with no sale restrictions in the total share capital (%)', 'S1040_0110_9'],
        ['Proportion of total shares in the total share capital (%)', 'S1040_0160_9']
      ],
      sqlid: 'COMMON_MAP_GBJG_C',
      fommatter: function () {
        var datas = arguments[0],
          result = [];

        var obj = infoObj.yearObj();
        if (datas && datas.length > 0) {
          for (var i = 0; i < datas.length; i++) {
            var data = datas[i];
            obj[iscompare ? data.STOCK_ID.replace('.SS', '') : data.REPORT_YEAR].push(data);
          }
        }
        var _obj = [],
          j = 0;
        $(Object.keys(obj)).each(function (i, k) {
          _obj[i] = obj[k];
        })
        for (var i = _obj.length - 1; i >= 0; i--) {
          result[j] = result[j] || {};
          $(_obj[i]).each(function (i, o) {
            var keys = Object.keys(o);
            result[j]['REPORT_YEAR'] = o.REPORT_YEAR;
            $(keys).each(function (k, key) {
              result[j][key + '_' + o.S1040_0000] = o[key];
            })
          })
          j++
        }
        return result;
      }
    },
    js_bs: {
      chinese: '资产负债表',
      prefix: [''],
      rowname: [
        ['Indicator/Year', 'REPORT_YEAR'],
        ['Monetary funds (yuan)', 'S2010_0010'],
        ['Settlement reserve (yuan)', 'S2010_0020'],
        ['Borrowed funds (yuan)', 'S2010_0030'],
        ['Tradable financial assets (yuan)', 'S2010_0040'],
        ['Bills receivable (yuan)', 'S2010_0050'],
        ['Accounts receivable (yuan)', 'S2010_0060'],
        ['Prepaid accounts (yuan)', 'S2010_0070'],
        ['Premium receivable (yuan)', 'S2010_0080'],
        ['Reinsurance accounts receivable (yuan)', 'S2010_0090'],
        ['Provision for reinsurance contract receivable (yuan)', 'S2010_0100'],
        ['Interest receivable (yuan)', 'S2010_0110'],
        ['Dividend receivable (yuan)', 'S2010_0120'],
        ['Other receivables (yuan)', 'S2010_0130'],
        ['Buy-in resale financial assets (yuan)', 'S2010_0140'],
        ['Inventory (yuan)', 'S2010_0150'],
        ['Non-current assets due within one year (yuan)', 'S2010_0160'],
        ['Other current assets (yuan)', 'S2010_0170'],
        ['Total current assets (yuan)', 'S2010_0180'],
        ['Loans and advances (yuan)', 'S2010_0190'],
        ['Available-for-sale financial assets (yuan)', 'S2010_0200'],
        ['Held-to-maturity investment (yuan)', 'S2010_0210'],
        ['Long-term receivables (yuan)', 'S2010_0220'],
        ['Long-term equity investment (yuan)', 'S2010_0230'],
        ['Investment real estate (yuan)', 'S2010_0240'],
        ['Net fixed assets (yuan)', 'S2010_0250'],
        ['Construction in progress (yuan)', 'S2010_0260'],
        ['Engineering materials (yuan)', 'S2010_0270'],
        ['Fixed assets clearance (yuan)', 'S2010_0280'],
        ['Productive biological assets (yuan)', 'S2010_0290'],
        ['Oil and gas assets (yuan)', 'S2010_0300'],
        ['Intangible assets (yuan)', 'S2010_0310'],
        ['Development expenditure (yuan)', 'S2010_0320'],
        ['Goodwill (yuan)', 'S2010_0330'],
        ['Long-term deferred expenses (yuan)', 'S2010_0340'],
        ['Total deferred tax debits (yuan)', 'S2010_0350'],
        ['Other long-term assets (yuan)', 'S2010_0360'],
        ['Total non-current assets (yuan)', 'S2010_0370'],
        ['Total assets (yuan)', 'S2010_0380'],
        ['Short-term loans (yuan)', 'S2010_0390'],
        ['Borrowing from the Central Bank (yuan)', 'S2010_0400'],
        ['Deposit absorption and interbank deposit (yuan)', 'S2010_0410'],
        ['Borrowed funds (yuan)', 'S2010_0420'],
        ['Transactional financial liabilities (yuan)', 'S2010_0430'],
        ['Bills payable (yuan)', 'S2010_0440'],
        ['Accounts payable (yuan)', 'S2010_0450'],
        ['Advance receipts (yuan)', 'S2010_0460'],
        ['Selling repurchase financial assets (yuan)', 'S2010_0470'],
        ['Fees and commissions payable (yuan)', 'S2010_0480'],
        ['Employee payable (yuan)', 'S2010_0490'],
        ['Tax payable (yuan)', 'S2010_0500'],
        ['Interest payable (yuan)', 'S2010_0510'],
        ['Dividend payable (yuan)', 'S2010_0520'],
        ['Other payables (yuan)', 'S2010_0530'],
        ['Reinsurance accounts payable (yuan)', 'S2010_0540'],
        ['Insurance contract reserve (yuan)', 'S2010_0550'],
        ['Agent trading securities (yuan)', 'S2010_0560'],
        ['Agent underwriting securities (yuan)', 'S2010_0570'],
        ['Long-term liabilities due within one year (yuan)', 'S2010_0580'],
        ['Other current liabilities (yuan)', 'S2010_0590'],
        ['Total current liabilities (yuan)', 'S2010_0600'],
        ['Long-term loans (yuan)', 'S2010_0610'],
        ['Bonds payable (yuan)', 'S2010_0620'],
        ['Long-term payables (yuan)', 'S2010_0630'],
        ['Special payables (yuan)', 'S2010_0640'],
        ['Estimated liabilities (yuan)', 'S2010_0650'],
        ['Total deferred tax credit (yuan)', 'S2010_0660'],
        ['Other long-term liabilities (yuan)', 'S2010_0670'],
        ['Total long-term liabilities (yuan)', 'S2010_0680'],
        ['Total liabilities (yuan)', 'S2010_0690'],
        ['Share capital (yuan)', 'S2010_0700'],
        ['Capital reserve (yuan)', 'S2010_0710'],
        ['Treasury shares (yuan)', 'S2010_0720'],
        ['Surplus reserve (yuan)', 'S2010_0730'],
        ['General risk reserve (yuan)', 'S2010_0740'],
        ['Undistributed profit (yuan)', 'S2010_0750'],
        ['Foreign currency statement conversion difference (yuan)', 'S2010_0760'],
        ['Total equity attributable to owners of the parent company (yuan)', 'S2010_0770'],
        ['Minority shareholders\' equity (yuan)', 'S2010_0780'],
        ['Total shareholders\' equity (yuan)', 'S2010_0790'],
        ['Total liabilities and shareholders\' equity (yuan)', 'S2010_0800']
      ],
      sqlid: 'COMMON_MAP_BALANCESHEET_C',
      fommatter: function () {
        return infoObj.js_binfo.fommatter(arguments[0]);
      }
    },
    js_cf: {
      chinese: '现金流量表',
      prefix: [''],
      rowname: [
        ['Indicator/Year', 'REPORT_YEAR'],
        ['Cash received from sales of goods and services (yuan)', 'S2030_0010'],
        ['Net increase in customer deposits and interbank deposits (yuan)', 'S2030_0020'],
        ['Net increase in borrowings from the central bank (yuan)', 'S2030_0030'],
        ['Net increase in funds borrowed from other financial institutions (yuan)', 'S2030_0040'],
        ['Cash received from the original insurance contract premium (yuan)', 'S2030_0050'],
        ['Net cash received from reinsurance business (yuan)', 'S2030_0060'],
        ['Net increase in policyholder deposits and investment funds (yuan)', 'S2030_0070'],
        ['Net increase in disposal of trading financial assets (yuan)', 'S2030_0080'],
        ['Cash for interest, handling fee and commission (yuan)', 'S2030_0090'],
        ['Net increase in borrowed funds (yuan)', 'S2030_0100'],
        ['Net increase in repurchase business funds (yuan)', 'S2030_0110'],
        ['Refund of received taxes and fees (yuan)', 'S2030_0120'],
        ['Other cash received related to operating activities (yuan)', 'S2030_0130'],
        ['Subtotal of cash inflow from operating activities (yuan)', 'S2030_0140'],
        ['Cash paid for purchasing goods to receive labor services (yuan)', 'S2030_0150'],
        ['Net increase in customer loans and advances (yuan)', 'S2030_0160'],
        ['Net increase in deposits with central banks and interbanks (yuan)', 'S2030_0170'],
        ['Cash paid for the original insurance contract compensation (yuan)', 'S2030_0180'],
        ['Cash to pay interest, handling fee and commission (yuan)', 'S2030_0190'],
        ['Cash paid for policy dividends (yuan)', 'S2030_0200'],
        ['Cash paid to and for employees (yuan)', 'S2030_0210'],
        ['Various taxes and fees paid (yuan)', 'S2030_0220'],
        ['Other cash paid related to operating activities (yuan)', 'S2030_0230'],
        ['Subtotal of cash outflow from operating activities (yuan)', 'S2030_0240'],
        ['Net cash flow from operating activities (yuan)', 'S2030_0250'],
        ['Cash received in return of investment (yuan)', 'S2030_0260'],
        ['Cash received from investment income (yuan)', 'S2030_0270'],
        ['Cash recovered from disposal of fixed assets, intangible assets and other long-term assets (yuan)', 'S2030_0280'],
        ['Cash received by the selling subsidiary in cash received from the investment (yuan)', 'S2030_0290'],
        ['Other cash received related to investment activities (yuan)', 'S2030_0300'],
        ['Subtotal of cash inflow from investment activities (yuan)', 'S2030_0310'],
        ['Cash paid for the purchase and construction of fixed assets, intangible assets and other long-term assets (yuan)', 'S2030_0320'],
        ['Cash paid for investment (yuan)', 'S2030_0330'],
        ['Net increase in pledged loans (yuan)', 'S2030_0340'],
        ['Obtain net cash paid by subsidiaries and other business units (yuan)', 'S2030_0350'],
        ['Other cash paid related to investment activities (yuan)', 'S2030_0360'],
        ['Subtotal of cash outflow from investment activities (yuan)', 'S2030_0370'],
        ['Net cash flow from investment activities (yuan)', 'S2030_0380'],
        ['Cash received from investment (yuan)', 'S2030_0390'],
        ['In the cash received from the investment absorption, the subsidiary receives the cash received from the minority shareholders\' equity investment (yuan)', 'S2030_0400'],
        ['Cash received from loans (yuan)', 'S2030_0410'],
        ['Cash received from issuing bonds (yuan)', 'S2030_0420'],
        ['Receive other cash related to financing activities (yuan)', 'S2030_0430'],
        ['Subtotal of cash inflow from financing activities (yuan)', 'S2030_0440'],
        ['Cash paid for debt repayment (yuan)', 'S2030_0450'],
        ['Cash paid for distribution of dividend profits or interest payments (yuan)', 'S2030_0460'],
        ['Dividends paid to minority shareholders in cash paid for distribution of dividend profits or interest payments (yuan)', 'S2030_0470'],
        ['Other cash paid related to financing activities (yuan)', 'S2030_0480'],
        ['Subtotal of cash outflow from financing activities (yuan)', 'S2030_0490'],
        ['Net cash flow from financing activities (yuan)', 'S2030_0500'],
        ['Effect of exchange rate changes on cash (yuan)', 'S2030_0510'],
        ['Net increase in cash and cash equivalents (yuan)', 'S2030_0520'],
        ['Cash and cash equivalent balance (yuan)', 'S2030_0540']
      ],
      sqlid: 'COMMON_MAP_CASHFLOW_C',
      fommatter: function () {
        return infoObj.js_binfo.fommatter(arguments[0]);
      }
    },
    js_is: {
      chinese: '利润表',
      prefix: [''],
      rowname: [
        ['Indicator/Year', 'REPORT_YEAR'],
        ['Total operating income (yuan)', 'S2020_0010'],
        ['Operating income (yuan)', 'S2020_0020'],
        ['Financial assets interest income (yuan)', 'S2020_0030'],
        ['Premiums earned (yuan)', 'S2020_0040'],
        ['Fee and commission income (yuan)', 'S2020_0050'],
        ['Total operating cost (yuan)', 'S2020_0060'],
        ['Operating cost (yuan)', 'S2020_0070'],
        ['Financial assets interest expense (yuan)', 'S2020_0080'],
        ['Handling fees and commission expenses (yuan)', 'S2020_0090'],
        ['Surrender (yuan)', 'S2020_0100'],
        ['Net compensation expenses (yuan)', 'S2020_0110'],
        ['Net withdrawal of insurance contract reserve (yuan)', 'S2020_0120'],
        ['Policy bonus expenditure (yuan)', 'S2020_0130'],
        ['Reinsurance expenses (yuan)', 'S2020_0140'],
        ['Business tax and surcharge (yuan)', 'S2020_0150'],
        ['Selling expenses (yuan)', 'S2020_0160'],
        ['Management expenses (yuan)', 'S2020_0170'],
        ['Financial expenses (yuan)', 'S2020_0180'],
        ['Asset impairment loss (yuan)', 'S2020_0190'],
        ['Fair value change income (yuan)', 'S2020_0200'],
        ['Investment income (yuan)', 'S2020_0210'],
        ['Investment income from associates and joint ventures (yuan)', 'S2020_0220'],
        ['Exchange income (yuan)', 'S2020_0230'],
        ['Operating profit (yuan)', 'S2020_0240'],
        ['Non-operating income (yuan)', 'S2020_0250'],
        ['Non-operating expenses (yuan)', 'S2020_0260'],
        ['Net loss from disposal of non-current assets (yuan)', 'S2020_0270'],
        ['Total profit (yuan)', 'S2020_0280'],
        ['Income tax (yuan)', 'S2020_0290'],
        ['Net profit (yuan)', 'S2020_0300'],
        ['Net profit attributable to the owner of the parent company (yuan)', 'S2020_0310'],
        ['Minority shareholders\' profit and loss (yuan)', 'S2020_0320'],
        ['Basic earnings per share (yuan)', 'S2020_0330'],
        ['Diluted earnings per share (yuan)', 'S2020_0340']
      ],
      sqlid: 'COMMON_MAP_INCOMESTATEMENT_C',
      fommatter: function () {
        return infoObj.js_binfo.fommatter(arguments[0]);
      }
    },
    companies: {},
    yearList: [],
    yearObj: function () { //返回处理数据对象
      var _y = {};
      if (!iscompare) {
        $(this.yearList).each(function (i, obj) {
          _y[obj] = [];
        })
      }
      if (iscompare) {
        infoObj.yearList = [];
        $(stock_id.split(',')).each(function (i, obj) {
          _y[obj] = [];
          infoObj.yearList.push(obj);
        })
        infoObj.yearList.sort(function (a, b) {
          return Number(b) - Number(a);
        })
      }
      $(get_data()).each(function (i, obj) {
        infoObj.companies[obj.val] = obj.val2;
      })
      return _y;
    },
    getYears: function (s_id, r_p_id, callBack) { //获取年份列表
      ajaxFun({
        url: sseQueryURL + 'commonQuery.do',
        datas: {
          isPagination: false,
          sqlId: 'COMMON_MAP_MAXYEAR_L',
          STOCK_ID: s_id,
          REPORT_PERIOD_ID: r_p_id,
        }
      }, function (res) {
        infoObj.yearList = [];
        if (res && res.result && res.result.length > 0 && res.result[0].REPORT_YEAR != '-') {
          var year = Number(res.result[0].REPORT_YEAR || get_systemDate_global().substring(0, 4));
          if (iscompare) {
            infoObj.yearList.push(year);

          } else {
            for (var i = year; i > year - 5; i--) {
              infoObj.yearList.push(i);
            }
          }
        } else {
          var year = get_systemDate_global().substring(0, 4);
          if (iscompare) {
            infoObj.yearList.push(year);
          } else {
            for (var i = year; i > year - 5; i--) {
              infoObj.yearList.push(i);
            }
          }
        }
        callBack();
      })
    }
  };

  function showData(year) { //渲染数据
    var _active = $('.linkbar a.active').attr('id'),
      _infoObj = infoObj[_active] || infoObj.js_binfo;
    var bInfoObj = {
      url: sseQueryURL + 'commonQuery.do',
      datas: {
        isPagination: false,
        sqlId: _infoObj.sqlid,
        type: 'inParams',
        REPORT_YEAR: year ? year : infoObj.yearList.join(','),
        STOCK_ID: stock_id,
        REPORT_PERIOD_ID: reporttype.val(),
      }
    };
    ajaxFun(bInfoObj, function (res) {
      xbrlinfo.html(_showTableData(_infoObj, res.result));
    })
  }

  if (urlcode.test(stock_id)) {
    if (iscompare) {
      $('.js_announcement').remove();
    } else {
      $('.js_announcement').attr('href', '/markets/equities/list/announcements/?COMPANY_CODE=' + stock_id + '&STOCK_CODE=' + stock_id).find('em').show();
    }
    infoObj.getYears(stock_id.split(',')[0], reporttype.val(), function () {
      showData(iscompare ? $('.search_contentpc .js_year').val() : null);
    });
  } else {
    alert('Please enter six correct stock codes.');
  }

  $('.linkbar a').on('click', function () {
    var _id = $(this).attr('id');
    if (/js_topten|js_scs/g.test(_id) && /4000|4400/g.test(reporttype.val())) {
      alert('Quarterly reports do not include information on capital structure and top 10 shareholders.');
    } else {
      if (urlcode.test(stock_id)) {
        $(this).addClass('active').siblings().removeClass('active')
        infoObj.getYears(stock_id.split(',')[0], reporttype.val(), function () {
          showData(iscompare ? $('.search_contentpc .js_year').val() : null);
        });
      } else {
        alert('Please enter six correct stock codes.');
      }
    }
  })

  $('.search_contentpc #btnQuery').click(function () { //PC端获取输入信息
    var _id = $('.linkbar a.active').attr('id');
    if (/js_topten|js_scs/g.test(_id) && /4000|4400/g.test(reporttype.val())) {
      alert('Quarterly reports do not include information on capital structure and top 10 shareholders.');
    } else {
      if (iscompare) {
        var yeardom = $('.search_contentpc .js_year').val(); //获取年份
        showData(yeardom);
        leftclick();
      } else {
        if (/^(\d{6})$/.test($.trim($('.search_contentpc #inputCode').val()))) {
          stock_id = $.trim($('.search_contentpc #inputCode').val()); //获取证券代码
          $(this).addClass('active').siblings().removeClass('active')
          infoObj.getYears(stock_id.split(',')[0], reporttype.val(), function () {
            showData();
          });
          leftclick();
        } else {
          alert('Please enter six correct stock codes.');
        }
      }
    }
  })

  $('.search_contentmobile #btnQuery').click(function () { //手机端搜索按钮
    var _id = $('.linkbar a.active').attr('id');
    if (/js_topten|js_scs/g.test(_id) && /4000|4400/g.test(reporttype.val())) {
      alert('Quarterly reports do not include information on capital structure and top 10 shareholders.');
    } else {
      if (/^(\d{6})$/.test($.trim($('.search_contentmobile #inputCode').val()))) {
        stock_id = $.trim($('.search_contentmobile #inputCode').val());
        infoObj.getYears(stock_id.split(',')[0], $('.js_reporttypemobile').val(), function () {
          showData();
        });
      } else {
        alert('Please enter six correct stock codes.');
      }
    }
  })
}

// 行业分类列表
var trade = [{
    id: 'A',
    name: "农、林、牧、渔业",
    enname: 'Agriculture, Forestry, Animal Husbandry & Fishery'
  },
  {
    id: 'B',
    name: "采矿业",
    enname: 'Mining'
  },
  {
    id: 'C',
    name: "制造业",
    enname: 'Manufacturing',
    children: [{
        name: "畜牧业",
        num: '03',
        enname: 'Animal Husbandry'
      },
      {
        name: "煤炭开采和洗煤",
        num: '06',
        enname: 'Coal Mining And Washing'
      },
      {
        name: "有色金属矿采",
        num: '09',
        enname: 'Nonferrous Metal Mining'
      },
      {
        name: "农副食品加工",
        num: '13',
        enname: 'Agricultural byproducts'
      },
      {
        name: "食品制造业",
        num: '14',
        enname: 'Food'
      },
      {
        name: "酒、饮料和精",
        num: '15',
        enname: 'Liquor, Beverage And Refined Tea'
      },
      {
        name: "纺织业",
        num: '17',
        enname: 'Textiles'
      },
      {
        name: "纺织服装、服",
        num: '18',
        enname: 'Textile & Apparels'
      },
      {
        name: "皮革、毛皮、",
        num: '19',
        enname: 'Leather, Fur, Feathers products & Footwear'
      },
      {
        name: "木材加工和木",
        num: '20',
        enname: 'Wood Processing & Wood, Bamboo, Rattan, Palm And Leather Products'
      },
      {
        name: "家具制造业",
        num: '21',
        enname: 'Furniture'
      },
      {
        name: "造纸和纸制品",
        num: '22',
        enname: 'Paper & Paper Products'
      },
      {
        name: "印刷和记录媒",
        num: '23',
        enname: 'Printing & Reproduction Of Recording Media '
      },
      {
        name: "文教、工美、",
        num: '24',
        enname: 'Cultural, Educational, Art, Craft, Sport And Recreational Products'
      },
      {
        name: "石油加工、炼",
        num: '25',
        enname: 'Petroleum Processing, Coking And Nuclear Fuel Processing'
      },
      {
        name: "化学原料和化",
        num: '26',
        enname: 'Chemical Raw Materials & Chemical Products'
      },
      {
        name: "医药制造业",
        num: '27',
        enname: 'Pharmaceuticals'
      },
      {
        name: "化学纤维制造",
        num: '28',
        enname: 'Chemical Fibers'
      },
      {
        name: "橡胶和塑料制",
        num: '29',
        enname: 'Rubber And Plastic Products'
      },
      {
        name: "非金属矿物制",
        num: '30',
        enname: 'Non-Metallic Mineral Products'
      },
      {
        name: "黑色金属冶炼",
        num: '31',
        enname: 'Ferrous Metals Castings And Forgings'
      },
      {
        name: "有色金属冶炼",
        num: '32',
        enname: 'Non Ferrous Metals Castings And Forgings'
      },
      {
        name: "金属制品业",
        num: '33',
        enname: 'Metals'
      },
      {
        name: "通用设备制造",
        num: '34',
        enname: 'General Equipments'
      },
      {
        name: "专用设备制造",
        num: '35',
        enname: 'Specialty Equipments'
      },
      {
        name: "汽车制造业",
        num: '36',
        enname: 'Automobiles'
      },
      {
        name: "铁路、船舶、",
        num: '37',
        enname: 'Railway, Shipbuilding, Aerospace And Other Transportation Equipment Manufacturing'
      },
      {
        name: "电气机械和器",
        num: '38',
        enname: 'Electrical Equipment And Machinery Manufacturing'
      },
      {
        name: "计算机、通信",
        num: '39',
        enname: 'Computer, Communication And Other Electronic Equipments'
      },
      {
        name: "仪器仪表制造",
        num: '40',
        enname: 'Instrumentation Manufacturing'
      },
      {
        name: "其他制造业",
        num: '41',
        enname: 'Other Manufacturing'
      },
      {
        name: "废弃资源综合",
        num: '42',
        enname: 'Comprehensive Utilization Of Waste Resources'
      },
    ],
  },
  {
    id: 'D',
    name: "电力、热力",
    enname: 'Electricity, Heat, Gas And Water Production And Supply'
  },
  {
    id: 'E',
    name: "建筑业",
    enname: 'Construction'
  },
  {
    id: 'F',
    name: "批发和零售业",
    enname: 'Wholesale & Retail'
  },
  {
    id: 'G',
    name: "交通运输、仓",
    enname: 'Transportation, Storage And Post'
  },
  {
    id: 'H',
    name: "住宿和餐饮业",
    enname: 'Lodging And Catering'
  },
  {
    id: 'I',
    name: "信息传输、软",
    enname: 'Information Transmission, Software And IT Services'
  },
  {
    id: 'J',
    name: "金融业",
    enname: 'Financial'
  },
  {
    id: 'K',
    name: "房地产业",
    enname: 'Real Estate'
  },
  {
    id: 'L',
    name: "租赁和商务服",
    enname: 'Leasing And Business Services'
  },
  {
    id: 'M',
    name: "科学研究和技",
    enname: 'Scientific Research And Technical Service'
  },
  {
    id: 'N',
    name: "水利、环境和",
    enname: 'Water Conservancy, Environment And Public Facilities Management'
  },
  {
    id: 'P',
    name: "教育",
    enname: 'Education'
  },
  {
    id: 'Q',
    name: "卫生和社会工",
    enname: 'Health And Social Work'
  },
  {
    id: 'R',
    name: "文化、体育和",
    enname: 'Culture, Sports And Entertainment'
  },
  {
    id: 'S',
    name: "综合",
    enname: 'Conglomerates'
  },
]

var thtmlArr = [],
  parms = {
    url: sseQueryURL + 'commonQuery.do',
    datas: {
      sqlId: "COMMON_MAP_HYFL_L",
      isPagination: false,
      CSRC_CODE: '',
      CSRC_GREAT_CODE: ''
    }
  }

thtmlArr.push('<ul class="lev1_block">');
$(trade).each(function (i, item) {
  var len = item.children && item.children.length > 0;
  thtmlArr.push('<li class="lev1 ' + (len ? 'lev1_open' : '') + '" id=' + item.id + ' title="' + item.enname + '">' + item.enname);
  thtmlArr.push(len ? '<ul class="lev2_block">' : '');
  $(item.children).each(function (index, childrenItem) {
    thtmlArr.push('<li class="lev2" id="' + item.id + '_' + childrenItem.num + '" title="' + childrenItem.enname + '">' + childrenItem.enname + '</li>');
  })
  thtmlArr.push((len ? '</ul>' : '') + '</li>');
})
thtmlArr.push('</ul>');
$('#js_myModel_compare #js_list').html(thtmlArr.join('')) //行业分类列表展示

// 行业分类公司列表
var iccompanies = {},
  iccompany = {};

function getCompanies(callBack) {
  if (Object.keys(iccompanies).length == 0) {
    ajaxFun({
      url: sseQueryURL + 'commonQuery.do',
      datas: {
        sqlId: "COMMON_MAP_HYFL_L",
        isPagination: false,
        CSRC_CODE: '',
        CSRC_GREAT_CODE: ''
      }
    }, function (data) {
      var resultData = data.result;
      if (resultData && resultData.length > 0) {
        $(resultData).each(function (i, obj) {
          if (obj.CSRC_CODE != 'C') {
            iccompanies[obj.CSRC_CODE] = iccompanies[obj.CSRC_CODE] || [];
            iccompanies[obj.CSRC_CODE].push(obj);
            iccompany[obj.COMPANY_CODE] = obj.CSRC_CODE;
          } else {
            iccompanies[obj.CSRC_CODE + '_' + obj.CSRC_GREAT_CODE] = iccompanies[obj.CSRC_CODE + '_' + obj.CSRC_GREAT_CODE] || [];
            iccompanies[obj.CSRC_CODE + '_' + obj.CSRC_GREAT_CODE].push(obj);
            iccompany[obj.COMPANY_CODE] = obj.CSRC_CODE + '_' + obj.CSRC_GREAT_CODE;
          }
        })
      }
      callBack();
    })
  } else {
    callBack();
  }
}

function showCompanies(id) {
  getCompanies(function () {
    var codejy = eval('/' + stock_id.split(',').join('|') + '/'),
      htmlArr = [];
    $(iccompanies[id]).each(function (i, obj) {
      htmlArr.push('<label class="complayname"><input type="checkbox" name="companyCodeList" value="' + obj.COMPANY_CODE + '" ' + (codejy.test(obj.COMPANY_CODE) ? 'checked="checked"' : '') + '><span>' + obj.COMPANY_ABBR + '<em>(' + obj.COMPANY_CODE + ')</em></span></label>');
    })
    if (htmlArr.length == 0) {
      htmlArr.push('<div>No Data Available!</div>');
    } else {
      htmlArr.push('<p style="text-align: left;float:left;font-size:14px;width:100%;">Note: You may select no more than 5 companies for comparison at the same time.</p>');
    }
    $('#js_myModel_compare #js_company').html(htmlArr.join(''));
  })
}

$('#js_myModel_compare #js_list li:not(.lev1_open)').click(function (e) {
  $('li.lev2,li.lev1').removeClass('active');
  $(this).addClass('active');
  var id = $(this).attr('id');
  showCompanies(id);
})

// 同行业比较提交
function checkSubmit() {
  var num = 5;
  // 根据查询框选择年报
  if (!$("input[type='checkbox']").is(':checked')) {
    alert("Please select at least one company for comparison.");
  } else if ($('input:checkbox[name="companyCodeList"]:checked').length > num) {
    alert("You may select no more than " + num + " companies for comparison at the same time.");
  } else {
    var companyCodeList = $(":checkbox").serialize();
    var stock_ids = companyCodeList.split('companyCodeList=').join('').replace(/&/g, ',');
    parent.window.location.href = '/markets/dataservice/xbrl/companyinfo/?stock_id=' + stock_ids + '&report_period_id=' + $('.js_reporttype').val() + '&iscompare=yes';
  }
}
// 同行业比较重置
function cleanCheckbox() {
  $('input:checkbox[name="companyCodeList"]:checked').prop('checked', false);
}
$('#js_submit').click(function () {
  checkSubmit()
})
$('#js_reset').click(function () {
  cleanCheckbox()
})

//同行业比较按钮
$('.sse_en_iconvs').on('click', function () {
  getCompanies(function () {
    var stockid = stock_id.split(',')[0];
    var codejy = eval('/' + stock_id.split(',').join('|') + '/'),
      htmlArr = [];
    $('#' + iccompany[stockid]).addClass('active');
    $(iccompanies[iccompany[stockid]]).each(function (i, obj) {
      htmlArr.push('<label class="complayname"><input type="checkbox" name="companyCodeList" value="' + obj.COMPANY_CODE + '" ' + (codejy.test(obj.COMPANY_CODE) ? 'checked="checked"' : '') + '><span>' + obj.COMPANY_ABBR + '<em>(' + obj.COMPANY_CODE + ')</em></span></label>');
    })
    if (htmlArr.length == 0) {
      htmlArr.push('<div>No Data Available!</div>');
    } else {
      htmlArr.push('<p style="text-align: left;float:left;font-size:14px;width:100%;">Note: You may select no more than 5 companies for comparison at the same time.</p>');
    }
    $('#js_myModel_compare #js_company').html(htmlArr.join(''));
  })
  $('#js_myModel_compare').show();
})

$(document).click(function (e) {
  var target = $(e.target);
  if (target.closest(".model-content").length == 0 && target.closest(".sse_en_iconvs").length == 0) {
    $('#js_myModel_compare').hide();
  }
})

function changeRT(dom, rtid) { //同步修改报告类型
  var rts = [];
  $(periodIdSelect).each(function (i, select) {
    rts.push('<option value="' + select[0] + '" ' + (rtid == select[0] ? 'selected="selected"' : '') + '>' + select[1] + '</option>');
  })
  $(dom).html(rts.join('')); //市场渲染
  require(["multipleSelect"], function () { //渲染下拉框
    multipleSelec(dom);
  });
  $(dom).on('change', function () {
    var rtmob = $(this).val();
    changeRT(dom == '.js_reporttypepc' ? '.js_reporttypemobile' : '.js_reporttypepc', rtmob)
  });
}

$(".js_reporttypepc").on('change', function () { //添加change事件
  var rtpc = $(this).val();
  changeRT('.js_reporttypemobile', rtpc)
});
$(".js_reporttypemobile").on('change', function () {
  var rtmob = $(this).val();
  changeRT('.js_reporttypepc', rtmob)
});

/**
 * 详情页逻辑代码
 */


if($(".js_companyinfotitle").length > 0){
  //获取URL传参
  var COMPANY_CODE = getValue("COMPANY_CODE");//公司代码
  var REPORT_PERIOD_ID = getValue("REPORT_PERIOD_ID");//报告类型1000半年报，5000年报
  var COMPANY_ABBR = decodeURI(getValue("COMPANY_ABBR"));//公司简称
  var REPORT_YEAR = getValue("REPORT_YEAR");//报告所属年度
  if(COMPANY_ABBR && COMPANY_CODE){
    $('.js_title').html(COMPANY_ABBR + '/' + COMPANY_CODE);
  }
  //获取当年年份
  var nowYear = new Date().getFullYear();
  //获取页面渲染数据
  var xbrlObjDetail = {
    url: sseQueryURL + 'commonSoaQuery.do',
    datas: {
      isPagination: false,
      sqlId: 'COMMON_SSE_PL_XBRL_YJGL_XQ',
      reportYear: [
        REPORT_YEAR,
        REPORT_YEAR - 1,
        REPORT_YEAR - 2,
        REPORT_YEAR - 3,
      ].join(),
      stockId: COMPANY_CODE,
    }
  };
  var pageArray = [];//接口数据
  //年报类型标题： js_companyinfotitle
  var title1 = "Annual report data(" + (REPORT_YEAR ? REPORT_YEAR : nowYear) + ")";
  var title2 = "Semi-annual report data(" + (REPORT_YEAR ? REPORT_YEAR : nowYear) + ")";
  $('.js_companyinfotitle').html(REPORT_PERIOD_ID == '1000' ? title2 : title1);//渲染标题
  //置空图表
  function settingAside() {
    $('#js_chanege_incomegrowth_svg').html('<div class="no-data">No data</div>');
    $('#js_chanege_netprofit_svg').html('<div class="no-data">No data</div>');
    $('.js_chanege_asset_svg').html('<div class="no-data">No data</div>');
    $('.js_chanege_asset_svg').attr('style', '');
    $('.js_chanege_asset_svg').parent().attr('style', '');
  }
  ajaxFun(xbrlObjDetail, function (data) {
    var resultData = data.result;
    pageArray = resultData;//存储接口数据
    if(pageArray &&  pageArray.length > 0){
      //半年报详情 ：js_table_companyinfodetail
      var detailArray = [];
      if(REPORT_PERIOD_ID == '1000'){
        detailArray[0] = pageArray[3];
      } else {
        detailArray[0] = pageArray[0];
      }
      var htmlStr = "<tbody>"+
        "<tr>"+
            "<td>Operating income (Ten thousand yuan)</td>"+
            "<td class='text-right'>" + (detailArray[0].S2020_0010 ? detailArray[0].S2020_0010 : '-') + "</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Net profit attributable to shareholders (Ten thousand yuan)</td>"+
            "<td class='text-right'>" + (detailArray[0].S2090_0040 ? detailArray[0].S2090_0040 : '-') + "</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Net profit attributable to shareholders after deducting non-recurring gains and losses (Ten thousand yuan)</td>"+
            "<td class='text-right'>" + (detailArray[0].S2090_0050 ? detailArray[0].S2090_0050 : '-') + "</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Operating cash flows(Ten thousand yuan)</td>"+
            "<td class='text-right'>" + (detailArray[0].S2090_0060 ? detailArray[0].S2090_0060 : '-') + "</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Return on equity (%)</td>"+
            "<td class='text-right'>" + (detailArray[0].S2090_0130 ? detailArray[0].S2090_0130 : '-') + "</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Basic earnings per share (Yuan)</td>"+
            "<td class='text-right'>"+ (detailArray[0].S2090_0090 ? detailArray[0].S2090_0090 : '-') + "</td>"+
        "</tr>"+
        "<tr>"+
          "<td>Asset-liability ratio（%）</td>"+
          "<td class='text-right'>" + (detailArray[0].assteration ? detailArray[0].assteration : '-') + "</td>"+
        "</tr>"+
      "</tbody>";  
      $(".js_table_companyinfodetail").html(htmlStr);
    } else {
      var htmlStr = "<tbody>"+
        "<tr>"+
            "<td>Operating income (Ten thousand yuan)</td>"+
            "<td class='text-right'>-</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Net profit attributable to shareholders (Ten thousand yuan)</td>"+
            "<td class='text-right'>-</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Net profit attributable to shareholders after deducting non-recurring gains and losses (Ten thousand yuan)</td>"+
            "<td class='text-right'>-</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Operating cash flows(Ten thousand yuan)</td>"+
            "<td class='text-right'>-</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Return on equity (%)</td>"+
            "<td class='text-right'>-</td>"+
        "</tr>"+
        "<tr>"+
            "<td>Basic earnings per share (Yuan)</td>"+
            "<td class='text-right'>-</td>"+
        "</tr>"+
        "<tr>"+
          "<td>Asset-liability ratio（%）</td>"+
          "<td class='text-right'>-</td>"+
        "</tr>"+
      "</tbody>";  
      $(".js_table_companyinfodetail").html(htmlStr);
    }
    //图表渲染数据
    var newArray = [];//图表一、二数据
    var newArray2 = [];//图表三数据
    if (resultData && resultData.length > 0) {
      if(resultData.length == 6){
        if(REPORT_PERIOD_ID == '1000'){
          newArray[0] = resultData[3];
          newArray[1] = resultData[4];
          newArray[2] = resultData[5];
          newArray2[0] = resultData[3];
          newArray2[1] = resultData[1];
          newArray2[2] = resultData[2];
        } else {
          newArray[0] = resultData[0];
          newArray[1] = resultData[1];
          newArray[2] = resultData[2];
          newArray2[0] = resultData[0];
          newArray2[1] = resultData[1];
          newArray2[2] = resultData[2];
        }

        var hidestate = false;//图表隐藏状态 false：隐藏  true：显示
        if(newArray[0].S2020_0010 != '-' || newArray[0].S2090_0040 != '-' || newArray[0].S2090_0050 != '-' || newArray[0].S2090_0060 != '-' || newArray[0].S2090_0130 != '-' || newArray[0].S2090_0090 != '-' || newArray[0].assteration != '-'){
            hidestate = true;
        }
        if(!hidestate){
          settingAside();
          return;
        } else {
          var assetHtml = '<div id="figure_container_one" style="width:200px; height:200px; margin:0 auto"></div>'+
          '<div id="figure_container_two" style="width:200px; height:200px; margin:0 auto"></div>'+
          '<div id="figure_container_three" style="width:200px; height:200px; margin:0 auto"></div>'
          $('.js_chanege_asset_svg').attr('style', 'max-width: 800px;margin: 0 auto;width: 100%;display: flex;flex-direction: row;');
          $('.js_chanege_asset_svg').html(assetHtml);
        }
        //图表一：js_chanege_incomegrowth_svg
        //图表二：js_chanege_netprofit_svg
        var type_detail = REPORT_PERIOD_ID;
        var newParam = {
            yearList: [],
            businessList: [],
            rateList: [],
            profitList: [],
            noProfitList: [],
            liabilities: [],
        };
        for (var i = 0; i < newArray.length; i++) {
            newParam.yearList.unshift(newArray[i].REPORT_YEAR);
            var businessOne = newArray[i].S2020_0010.split(",").reduce(function (
                total,
                current
            ) {
                return (total += current);
            });
            newParam.businessList.unshift(
                isNaN(Number(businessOne)) ? null : Number(businessOne)
            );
            newParam.rateList.unshift(
                isNaN(Number(newArray[i].growthRate)) ? null : Number(newArray[i].growthRate)
            );
            newParam.liabilities.unshift({
                yearValue: newArray[i].REPORT_YEAR,
                assteration: isNaN(Number(newArray[i].assteration))
                    ? null
                    : Number(newArray[i].assteration),
            });
            var profitOne = newArray[i].S2090_0040.split(",").reduce(function (
                total,
                current
            ) {
                return (total += current);
            });
            newParam.profitList.unshift(
                isNaN(Number(profitOne)) ? null : Number(profitOne)
            );
            var profitTwo = newArray[i].S2090_0050.split(",").reduce(function (
                total,
                current
            ) {
                return (total += current);
            });
            newParam.noProfitList.unshift(
                isNaN(Number(profitTwo)) ? null : Number(profitTwo)
            );
        }
        drawColumn(newParam,type_detail);
        DrawRowTwo(newParam,type_detail);

        /**
         * 饼状图数据处理
         * 图表三：js_chanege_asset_svg
         */
        var newParam2 = {
            yearList: [],
            businessList: [],
            rateList: [],
            profitList: [],
            noProfitList: [],
            liabilities: [],
        },
        isNullTotal = 0;
        for (var i = 0; i < newArray2.length; i++) {
            newParam2.yearList.unshift(newArray2[i].REPORT_YEAR);
            var businessOne = newArray2[i].S2020_0010.split(",").reduce(function (
                total,
                current
            ) {
                return (total += current);
            });
            newParam2.businessList.unshift(
                isNaN(Number(businessOne)) ? null : Number(businessOne)
            );
            newParam.rateList.unshift(
                isNaN(Number(newArray2[i].growthRate)) ? null : Number(newArray2[i].growthRate)
            );
            newParam2.liabilities.unshift({
                yearValue: newArray2[i].REPORT_YEAR,
                assteration: isNaN(Number(newArray2[i].assteration))
                    ? null
                    : Number(newArray2[i].assteration),
            });
            if (isNaN(Number(newArray2[i].assteration))) {
                isNullTotal += 1;
            }
            var profitOne = newArray2[i].S2090_0040.split(",").reduce(function (
                total,
                current
            ) {
                return (total += current);
            });
            newParam2.profitList.unshift(
                isNaN(Number(profitOne)) ? null : Number(profitOne)
            );
            var profitTwo = newArray2[i].S2090_0050.split(",").reduce(function (
                total,
                current
            ) {
                return (total += current);
            });
            newParam2.noProfitList.unshift(
                isNaN(Number(profitTwo)) ? null : Number(profitTwo)
            );
        }
        if (isNullTotal == 3) {
          $('.js_chanege_asset_svg').html('<div class="no-data">No data</div>');
          $('.js_chanege_asset_svg').attr('style', '');
          $('.js_chanege_asset_svg').parent().attr('style', '');
        } else {
          drawPanIcon(newParam2,type_detail);
        }
      } else {
        settingAside();
      }
    } else {
      settingAside();
    }
  })
}