from bs4 import BeautifulSoup
from requests_ntlm import HttpNtlmAuth
import requests
import json
import mimetypes
import os
from urllib.parse import urlparse

# global constants/variables are prefixed with G_

G_CMS_BASE_URL='https://cms.giu-uni.de'
G_CMS_ALL_COURSES_PAGE='/apps/student/ViewAllCourseStn'
G_NTLM_AUTH = None
G_ROOT_DIR= './cms_dir_test/'
G_SYMS_INVALID_IN_FILENAME="<>:\"/\|?*"


def make_filename_compatible(filename):
    out = ""
    for c in filename:
        if c in G_SYMS_INVALID_IN_FILENAME:
            out+="--"
        else:
            out+=c
    return out

def get_ntlm_credentials(fileLoc):
    with open(fileLoc) as _secret:
        secret = json.load(_secret)
        return HttpNtlmAuth(secret['username'],secret['pass'])


def get_course_content(html_str):

    document = BeautifulSoup(html_str,'html.parser')
    contents = []

    for weekNode in document.find_all(class_='weeksdata'):
        weekNodeLinks = [ n.get('href') for n in weekNode.find_all(class_='btn btn-primary contentbtn')]
        current_node = weekNode.find_all(class_='card-body')
        weekNodeContentLabels = [ n.div.text for n in current_node]

        assert(len(weekNodeContentLabels)==len(weekNodeLinks))

        for i in range(len(weekNodeContentLabels)):
            contents+=[{
                'label' : weekNodeContentLabels[i],
                'link' : G_CMS_BASE_URL + weekNodeLinks[i],
                }]

    return contents


def get_url_course_page(courseId,seasonid):
    return '/apps/student/CourseViewStn.aspx?id='+courseId+'&sid='+seasonid

def get_course_and_season_infos(html_str):

    seasons = []

    document = BeautifulSoup(html_str,'html.parser')
    courseTables = document.find_all(class_='col-md-12 col-lg-12 col-sm-12')

    for ct in courseTables:

        season = {}
        seasonInfoNode = ct.find(class_='menu-header-title')


        if seasonInfoNode and seasonInfoNode.text[0:6]=='Season':

            s_split = seasonInfoNode.text.split()
            season['id'] = s_split[2]
            season['title'] = s_split[5] + ' ' + s_split[6]
            season['courses'] = []

        courseRows = ct.find_all('tr')[1:]

        for cr in courseRows:
            cols = cr.find_all('td')
            courseId = cols[-2].text
            courseName = cols[1].text
            season['courses']+= [{
                'title' : courseName,
                'link' : G_CMS_BASE_URL + get_url_course_page(courseId,season['id'])
                }]

        if season:
            seasons+=[season]

    return seasons


def construct_season_directory_tree(season):
    dirs = []

    rootDir=season['title']
    print(rootDir)

    for course in season['courses']:
        dirs+=[(rootDir+'/'+course['title']+'/')]

    return dirs


G_NTLM_AUTH = get_ntlm_credentials('./account.json')

def sync_all_content(season):
    dirs = construct_season_directory_tree(season)

    for i,c in enumerate(season['courses']):
        print("downloading contents of \'{}\'".format(c['title']))
        courseDir = G_ROOT_DIR+dirs[i]
        os.makedirs(courseDir,exist_ok=True)
        sync_course(c,courseDir)

def sync_course(course,courseDir):

    print('fetching page for course \'{}\''.format(course['title']))
    print('GET : \'{}\''.format(course['link']))

    try:
        coursePageReq = requests.get(course['link'],auth=G_NTLM_AUTH)
    except requests.exceptions.RequestException as e:
        print('PAGE FETCHING ERROR : ',e)
        return

    courseContents = get_course_content(coursePageReq.content)

    for content in courseContents:
        print("found content \'{}\', starting download".format(content['label']))

        content_url_path = urlparse(content['link']).path
        content_ext = os.path.splitext(content_url_path)[1]
        filePath = courseDir+make_filename_compatible(content['label'])+content_ext

        if os.path.isfile(filePath):
            print("content already exists")
            continue

        print('GET : \'{}\''.format(content['link']))

        try:
            contentRawStream = requests.get(content['link'],auth=G_NTLM_AUTH)

        except requests.exceptions.RequestException as e:
            print('CONTENT FETCHING ERROR : ',e)
            return

        print('saving as :',filePath)
        with open(filePath,'wb') as f:
            f.write(contentRawStream.content)



seasons = get_course_and_season_infos(html_str)
sync_all_content(seasons[0])



