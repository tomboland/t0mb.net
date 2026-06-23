{-# LANGUAGE OverloadedStrings #-}

import Data.Monoid ((<>))
import Hakyll
import System.FilePath (replaceExtension)

main :: IO ()
main = hakyll $ do
    match "css/*" $ do
        route idRoute
        compile compressCssCompiler

    match imagePattern $ do
        route idRoute
        compile copyFileCompiler

    match "posts/*/index.md" $ do
        route cleanPostRoute
        compile $
            pandocCompiler
                >>= saveSnapshot "content"
                >>= loadAndApplyTemplate "templates/post.html" postCtx
                >>= loadAndApplyTemplate "templates/default.html" siteCtx
                >>= relativizeUrls

    create ["index.html"] $ do
        route idRoute
        compile $ do
            posts <- fmap (take 20) . recentFirst =<< loadAllSnapshots "posts/*/index.md" "content"

            let indexCtx =
                    listField "posts" postCtx (return posts)
                    <> constField "title" "t0mb.net"
                    <> siteCtx

            makeItem ""
                >>= loadAndApplyTemplate "templates/post-list.html" indexCtx
                >>= loadAndApplyTemplate "templates/default.html" indexCtx
                >>= relativizeUrls

    create ["archive.html"] $ do
        route idRoute
        compile $ do
            posts <- recentFirst =<< loadAllSnapshots "posts/*/index.md" "content"

            let archiveCtx =
                    listField "posts" postCtx (return posts)
                    <> constField "title" "archive"
                    <> siteCtx

            makeItem ""
                >>= loadAndApplyTemplate "templates/archive.html" archiveCtx
                >>= loadAndApplyTemplate "templates/default.html" archiveCtx
                >>= relativizeUrls

    create ["rss.xml"] $ do
        route idRoute
        compile $ do
            posts <- fmap (take 20) . recentFirst =<< loadAllSnapshots "posts/*/index.md" "content"
            renderRss feedConfig feedCtx posts

    match "templates/*" $ compile templateBodyCompiler

    match "software.md" $ do
        route $ setExtension "html"
        compile $
            pandocCompiler
                >>= loadAndApplyTemplate "templates/default.html" siteCtx
                >>= relativizeUrls

imagePattern :: Pattern
imagePattern =
    "posts/**.jpg"
    .||. "posts/**.jpeg"
    .||. "posts/**.png"
    .||. "posts/**.gif"
    .||. "posts/**.webp"
    .||. "posts/**.avif"

cleanPostRoute :: Routes
cleanPostRoute =
    customRoute $ \identifier ->
        replaceExtension (toFilePath identifier) "html"

siteCtx :: Context String
siteCtx =
    constField "siteTitle" "t0mb.net"
    <> constField "siteDescription" "Brain spill"
    <> constField "builtWith" "Site built with <a href=https://jaspervdj.be/hakyll/>Hakyll</a>"
    <> defaultContext

postCtx :: Context String
postCtx =
    dateField "date" "%Y-%m-%d"
    <> defaultContext

feedCtx :: Context String
feedCtx =
    postCtx
    <> bodyField "description"

feedConfig :: FeedConfiguration
feedConfig = FeedConfiguration
    { feedTitle       = "t0mb.net"
    , feedDescription = "Brain spill"
    , feedAuthorName  = "Tom Boland"
    , feedAuthorEmail = ""
    , feedRoot        = "https://t0mb.net"
    }
